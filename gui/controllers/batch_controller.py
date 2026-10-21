"""逐来源批量编排；材料与实测 S 参数使用各自正式 API。"""
import json
import logging
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from core import __version__
from core.reuse import index_completed_runs, run_key, sha256_file
from export.csv_safety import escape_formula_cells
from export.excel_export import export_batch_excel
from export.provenance import git_state
from gui.controllers.analysis_controller import SUPPORTED, Cancelled, analyze_request, inspect_file
from gui.controllers.comparison_controller import comparison_hashes
from gui.controllers.quality_controller import quality_rows
from gui.controllers.sparameter_controller import analyze_s_request
from run_batch import summarize_sample


def scan_folder(folder, parser_options, progress, cancelled):
    """只扫描所选目录的直接文件，避免导入输出目录或环境。"""
    paths = sorted(p for p in Path(folder).iterdir() if p.is_file() and not p.is_symlink() and p.suffix.lower() in SUPPORTED)
    items = []
    for i, path in enumerate(paths):
        if cancelled():
            raise Cancelled("扫描已取消")
        options = dict(parser_options)
        if path.suffix.lower() == ".memp":
            options.pop("frequency_unit", None); options.pop("column_map", None)
        items.append(inspect_file(path, options))
        progress(int((i+1)*100/len(paths)), f"检查 {path.name}")
    return items


def _reuse_configuration(request):
    """与 analysis_service 写入记录的配置字段保持一致，用于哈希复用。"""
    return {"requested_frequency_range_ghz": [request.frequency_min, request.frequency_max],
            "requested_thickness_range_mm": [request.thickness_min, request.thickness_max],
            "thickness_step_mm": request.thickness_step, "curve_thickness_mm": request.curve_thickness,
            "rl_threshold_db": request.threshold, "eab_threshold_crossing": request.eab_crossing,
            "parser_options": dict(request.parser_options),
            "quarter_wave_orders": list(request.quarter_wave_orders),
            "impedance_tolerance": request.impedance_tolerance}


def run_batch_requests(requests, output, progress, cancelled, member_update=lambda r: None, reuse=False):
    if not requests:
        raise ValueError("目录没有可分析文件。")
    directory = Path(output) / "batches" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:10])
    directory.mkdir(parents=True)
    members = [dict(sample=r.name, raw_file=str(r.path), kind="Measured S Parameters" if r.path.suffix.lower()==".sdat" else "Calculated RL", status="not_started") for r in requests]
    record = dict(software_version=__version__, git=git_state(), analysis_date=datetime.now().astimezone().isoformat(),
                  status="started", interpolation="OFF", members=members, progress_log="members.jsonl",
                  reuse_completed_runs=bool(reuse), reused_count=0)
    summaries, minima, bands, provenance = [], [], [], []
    indexes = {}

    def update_counts():
        for state in ("success", "failed", "cancelled", "not_started"):
            record[state+"_count"] = sum(m["status"] == state for m in members)
        record["warning_count"] = sum(bool(m.get("warnings")) for m in members)

    def save():
        update_counts()
        target = directory / "batch_record.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)

    def append_member(index, member):
        """逐个样品追加进度日志，避免每完成一个就重写完整批次记录。"""
        with (directory / "members.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"index": index, **member}, ensure_ascii=False) + "\n")

    save()
    try:
        for index, (request, member) in enumerate(zip(requests, members)):
            if cancelled():
                record["status"] = "cancelled"
                break
            member["status"] = "running"; member_update(dict(member, index=index))
            report = lambda value, text: progress(int((index+value/100)*100/len(requests)), f"{index+1}/{len(requests)} {request.name}: {text}")
            try:
                cached = None
                if reuse and request.path.suffix.lower() != ".sdat":
                    root = str(Path(request.output).resolve())
                    if root not in indexes:
                        indexes[root] = index_completed_runs(root)
                    cached = indexes[root].get(run_key(request.name, sha256_file(request.path),
                                                       _reuse_configuration(request)))
                if cached is not None:
                    cached_record = json.loads((cached / "analysis_record.json").read_text(encoding="utf-8"))
                    summary, points, eab, source = summarize_sample(request.name, cached)
                    summaries.append(summary); minima.extend(points); bands.extend(eab)
                    provenance.append([request.name, "Reused run", str(cached)])
                    member.update(status="success", run_directory=str(cached), reused_from=str(cached),
                                  quality_control=quality_rows(cached_record),
                                  validation=cached_record.get("validation_status", "pending"),
                                  warnings=cached_record.get("warnings", []))
                    record["reused_count"] += 1
                else:
                    if request.path.suffix.lower() == ".sdat":
                        result = analyze_s_request(request.path, request.name, directory/"sources", "", report, cancelled, dpi=request.dpi)
                    else:
                        result = analyze_request(replace(request, output=directory/"sources"), report, cancelled)
                        summary, points, eab, source = summarize_sample(request.name, result["directory"])
                        summaries.append(summary); minima.extend(points); bands.extend(eab)
                        provenance.append([request.name, "Run", str(result["directory"])])
                        if reuse:
                            key = run_key(request.name, source.get("raw_sha256"), _reuse_configuration(request))
                            indexes.setdefault(str(Path(request.output).resolve()), {})[key] = result["directory"]
                    member.update(status="success", run_directory=str(result["directory"]),
                                  quality_control=quality_rows(result["record"]),
                                  validation=result["record"].get("schema_status", result["record"].get("validation_status", "pending")),
                                  warnings=result["record"].get("warnings", []) + result["record"].get("quality_checks", {}).get("warnings", []))
                    from plotting.style import plt
                    for fig in result.get("figures", {}).values():
                        plt.close(fig)
                    del result
            except Cancelled as error:
                member.update(status="cancelled", error=str(error)); record["status"] = "cancelled"
            except Exception as error:
                logging.getLogger("microwave.gui").exception("批量来源失败：%s", request.path)
                member.update(status="failed", error=f"{type(error).__name__}: {error}")
                member["quality_control"] = quality_rows(member)
            append_member(index, member); member_update(dict(member, index=index))
            if record["status"] == "cancelled":
                break
        if record["status"] != "cancelled":
            update_counts()
            record["status"] = "partial_failure" if record["failed_count"] and record["success_count"] else "failed" if record["failed_count"] else "success"
        escape_formula_cells(pd.DataFrame([{k:v for k,v in m.items() if k not in {"quality_control", "warnings"}} for m in members])).to_csv(directory/"sources.csv", index=False)
        if summaries:
            export_batch_excel(directory/"materials_summary.xlsx", summaries, minima, bands, provenance)
        record["artifacts_sha256"] = comparison_hashes(directory)
        save()
        progress(100 if record["status"] != "cancelled" else int(sum(m["status"] in {"success", "failed"} for m in members)*100/len(members)), "批量任务"+record["status"])
        return dict(directory=directory, record=record)
    except Exception as error:
        record.update(status="failed", error=str(error)); save()
        raise
