"""逐来源批量编排；材料与实测 S 参数使用各自正式 API。"""
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import json
import logging
import uuid
import pandas as pd
from core import __version__
from export.provenance import git_state
from export.excel_export import export_batch_excel
from run_batch import summarize_sample
from gui.controllers.analysis_controller import SUPPORTED, inspect_file, analyze_request, Cancelled
from gui.controllers.sparameter_controller import analyze_s_request
from gui.controllers.comparison_controller import comparison_hashes
from gui.controllers.quality_controller import quality_rows


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


def run_batch_requests(requests, output, progress, cancelled, member_update=lambda r: None):
    if not requests:
        raise ValueError("目录没有可分析文件。")
    directory = Path(output) / "batches" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:10])
    directory.mkdir(parents=True)
    members = [dict(sample=r.name, raw_file=str(r.path), kind="Measured S Parameters" if r.path.suffix.lower()==".sdat" else "Calculated RL", status="not_started") for r in requests]
    record = dict(software_version=__version__, git=git_state(), analysis_date=datetime.now().astimezone().isoformat(),
                  status="started", interpolation="OFF", members=members)
    summaries, minima, bands, provenance = [], [], [], []

    def save():
        for state in ("success", "failed", "cancelled", "not_started"):
            record[state+"_count"] = sum(m["status"] == state for m in members)
        record["warning_count"] = sum(bool(m.get("warnings")) for m in members)
        target = directory / "batch_record.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)

    save()
    try:
        for index, (request, member) in enumerate(zip(requests, members)):
            if cancelled():
                record["status"] = "cancelled"
                break
            member["status"] = "running"; save(); member_update(dict(member, index=index))
            report = lambda value, text: progress(int((index+value/100)*100/len(requests)), f"{index+1}/{len(requests)} {request.name}: {text}")
            try:
                if request.path.suffix.lower() == ".sdat":
                    result = analyze_s_request(request.path, request.name, directory/"sources", "", report, cancelled, dpi=request.dpi)
                else:
                    result = analyze_request(replace(request, output=directory/"sources"), report, cancelled)
                    summary, points, eab, source = summarize_sample(request.name, result["directory"])
                    summaries.append(summary); minima.extend(points); bands.extend(eab)
                    provenance.append([request.name, "Run", str(result["directory"])])
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
            save(); member_update(dict(member, index=index))
            if record["status"] == "cancelled":
                break
        if record["status"] != "cancelled":
            record["status"] = "partial_failure" if record["failed_count"] and record["success_count"] else "failed" if record["failed_count"] else "success"
        pd.DataFrame([{k:v for k,v in m.items() if k not in {"quality_control", "warnings"}} for m in members]).to_csv(directory/"sources.csv", index=False)
        if summaries:
            export_batch_excel(directory/"materials_summary.xlsx", summaries, minima, bands, provenance)
        record["artifacts_sha256"] = comparison_hashes(directory)
        save()
        progress(100 if record["status"] != "cancelled" else int(sum(m["status"] in {"success", "failed"} for m in members)*100/len(members)), "批量任务"+record["status"])
        return dict(directory=directory, record=record)
    except Exception as error:
        record.update(status="failed", error=str(error)); save()
        raise
