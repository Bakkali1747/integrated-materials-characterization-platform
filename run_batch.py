"""Phase 3 批次入口：单样品失败隔离、公共扫描配置、可追溯比较与 Excel 汇总。"""

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from core import __version__
from core.batch import ANALYSIS_KEYS, discover_samples, load_manifest, validate_entries
from core.reuse import index_completed_runs, run_key, sha256_file
from core.sdat_inspector import inspect_sdat
from export.csv_safety import escape_formula_cells
from export.excel_export import export_batch_excel
from export.origin_export import save_figure_bundle
from export.provenance import git_state, json_safe
from plotting.comparison_plot import PARAMETERS, plot_comparison
from plotting.style import PlotStyle, plt
from run_analysis import analyze


def save_batch_record(directory, record):
    """输入批次目录与状态；保存完整 JSON/TXT，处理中、部分失败和成功有明确区分。"""
    text = json.dumps(json_safe(record), ensure_ascii=False, indent=2, allow_nan=False)
    for filename in ("batch_record.json", "batch_record.txt"):
        (directory/filename).write_text(text+"\n", encoding="utf-8")


def summarize_sample(name, directory):
    """输入成功的单样品目录；返回汇总及全部并列位置，保留标准 −10 dB EAB。"""
    record = json.loads((directory/"analysis_record.json").read_text(encoding="utf-8"))
    if record["status"] != "success":
        raise ValueError("不能将未成功的运行纳入结果汇总。")
    minimum = record["global_minima"][0]
    best = record["maximum_eab_details"]
    ranges = "; ".join(f"{b['start_ghz']:.6g}–{b['end_ghz']:.6g}" for b in best[0]["widest_bands"]) if best else ""
    summary = {"sample": name, "status": "success", "rl_min_db": minimum["rl_min_db"],
               "rl_min_frequency_ghz": minimum["frequency_ghz"], "best_thickness_mm": minimum["thickness_mm"],
               "maximum_eab_ghz": record["maximum_eab_ghz"], "thickness_at_maximum_eab_mm": best[0]["thickness_mm"] if best else None,
               "maximum_eab_frequency_ranges_ghz": ranges, "rl_min_tie_count": len(record["global_minima"]),
               "maximum_eab_thickness_tie_count": len(best), "validation": record["validation_status"],
               "frequency_min_ghz": record["frequency_range_ghz"][0], "frequency_max_ghz": record["frequency_range_ghz"][1],
               "run_directory": str(directory.resolve())}
    minima = [{"sample": name, **row} for row in record["global_minima"]]
    bands = [{"sample": name, "thickness_mm": entry["thickness_mm"], **band} for entry in best for band in entry["widest_bands"]]
    return summary, minima, bands, record


def compare_runs(runs, directory, style, curve_thickness, *, figure_callback=None):
    """输入选中的 name/运行目录；验证来源哈希后输出十项原生采样曲线和长表 CSV。

    不对不同频率网格自动对齐，不混用每个样品各自最佳厚度的 RL。
    """
    if not runs:
        return {"status": "no_successful_samples", "samples": []}
    directory.mkdir()
    loaded, grids = [], []
    for name, run in runs:
        record = json.loads((run/"analysis_record.json").read_text(encoding="utf-8"))
        tables = {}
        for filename in ("loss_parameters.csv", "RL_curve.csv", "thickness_summary.csv"):
            raw = (run/filename).read_bytes()
            if hashlib.sha256(raw).hexdigest() != record["artifacts_sha256"][filename]:
                raise ValueError(f"{name} 的 {filename} 在分析后已改变，拒绝比较。")
            tables[filename] = pd.read_csv(run/filename)
        if record["configuration"]["curve_thickness_mm"] != curve_thickness:
            raise ValueError("RL 比较必须使用相同指定厚度。")
        loaded.append((name, tables))
        grids.append(tables["loss_parameters.csv"].frequency_ghz.to_numpy())
    same_grid = all(np.array_equal(grids[0], grid) for grid in grids[1:])
    for metric in PARAMETERS:
        series, long_rows = [], []
        for name, tables in loaded:
            if metric == "rl_db":
                frame, axis = tables["RL_curve.csv"], "frequency_ghz"
            elif metric == "eab_minus10_db_ghz":
                frame, axis = tables["thickness_summary.csv"], "thickness_mm"
            else:
                frame, axis = tables["loss_parameters.csv"], "frequency_ghz"
            series.append({"name": name, "x": frame[axis].to_numpy(), "y": frame[metric].to_numpy()})
            long_rows.append(pd.DataFrame({"sample": name, axis: frame[axis], metric: frame[metric]}))
        escape_formula_cells(pd.concat(long_rows, ignore_index=True)).to_csv(directory/f"{metric}.csv", index=False)
        fig = plot_comparison(series, metric, style, curve_thickness)
        fig.suptitle("PENDING VALIDATION", fontsize=10, color="0.35")
        save_figure_bundle(fig, directory/f"{metric}.png", dpi=style.dpi, bbox_inches="tight")
        if figure_callback is not None:
            figure_callback(metric, fig)
        plt.close(fig)
    notes = ["所有曲线保留各自原始采样点；不插值、不外推。", "RL 比较使用公共指定厚度；EAB 使用 −10 dB 最大连续频段。",
             "虚部定义和商业软件对照状态见每个样品记录。"]
    if not same_grid:
        notes.append("[KNOWN] 所选样品频率网格不同；各自频率范围下的 RLmin/EAB 不能视为同条件优劣排名。")
    (directory/"comparison_notes.txt").write_text("\n".join(notes)+"\n", encoding="utf-8")
    return {"status": "success", "samples": [name for name, _ in runs], "identical_frequency_grids": same_grid,
            "interpolation": "OFF", "curve_thickness_mm": curve_thickness, "notes": notes}


def _reuse_configuration(options, parser):
    """与 analysis_service 的配置字段一致，仅比较影响数值结果的项。"""
    return {"requested_frequency_range_ghz": [options.get("frequency_min"), options.get("frequency_max")],
            "requested_thickness_range_mm": [options.get("thickness_min", 1.), options.get("thickness_max", 5.)],
            "thickness_step_mm": options.get("thickness_step", .01),
            "curve_thickness_mm": options.get("curve_thickness", 2.),
            "rl_threshold_db": options.get("threshold", -10.),
            "eab_threshold_crossing": options.get("eab_crossing", "linear"),
            "parser_options": dict(parser),
            "quarter_wave_orders": options.get("quarter_wave_orders", [1]),
            "impedance_tolerance": options.get("impedance_tolerance", .1)}


def analyze_batch(entries, *, output="output", analysis_options=None, compare_samples=None, style=None, source=None, skipped=(), reuse=False):
    """输入显式样品清单及公共扫描配置；返回批次目录，单文件失败不丢失其他结果。

    每个成员使用同一分析配置，解析配置可单独指定；汇总科学字段失败时为空。
    """
    validate_entries(entries)
    options = dict(analysis_options or {})
    if set(options)-ANALYSIS_KEYS:
        raise ValueError("未知公共分析配置。")
    selected = compare_samples if compare_samples is not None else [e["name"] for e in entries]
    if not selected or len(set(selected)) != len(selected) or set(selected)-{e["name"] for e in entries}:
        raise ValueError("比较样品必须是不重复且存在的名称。")
    style = style or PlotStyle()
    now = datetime.now().astimezone()
    directory = Path(output).resolve()/"batch"/(now.strftime("%Y%m%dT%H%M%S")+"_"+uuid.uuid4().hex[:12])
    directory.mkdir(parents=True, exist_ok=False)
    record = {"analysis_date": now.isoformat(timespec="seconds"), "software_version": __version__, "git": git_state(),
              "source": source, "analysis_options": options, "plot_style": vars(style), "samples_requested": entries,
              "compare_samples_requested": selected, "skipped_nondata_files": list(skipped), "status": "started", "members": []}
    if source and Path(source).is_file():
        record["manifest_sha256"] = hashlib.sha256(Path(source).read_bytes()).hexdigest()
    save_batch_record(directory, record)
    summaries, minima, bands, provenance, successful = [], [], [], [], []
    reuse_index = index_completed_runs(output) if reuse else {}
    try:
        for index, entry in enumerate(entries, 1):
            name = entry["name"]
            member_root = directory/"samples"/f"{index:04d}"
            print(f"[{index}/{len(entries)}] {name}")
            try:
                cached = None
                if reuse and Path(entry["path"]).suffix.lower() != ".sdat":
                    key = run_key(name, sha256_file(entry["path"]),
                                  _reuse_configuration(options, entry.get("parser", {})))
                    cached = reuse_index.get(key)
                if cached is not None:
                    run = cached
                    print(f"复用已完成运行：{run}")
                else:
                    run = analyze(entry["path"], output=member_root, name=name, style=style, **options, **entry.get("parser", {}))
                    if reuse and Path(entry["path"]).suffix.lower() != ".sdat":
                        reuse_index[key] = run
                summary, points, eab_bands, sample_record = summarize_sample(name, run)
                summaries.append(summary)
                minima.extend(points)
                bands.extend(eab_bands)
                successful.append((name, run))
                member = {"sample": name, "status": "success", "run_directory": str(run.resolve()),
                          **({"reused_from": str(run.resolve())} if cached is not None else {})}
                provenance.extend([[name, "Raw file", sample_record["raw_file"]], [name, "Raw SHA-256", sample_record["raw_sha256"]],
                                   [name, "Run directory", str(run.resolve())], [name, "Validation", sample_record["validation_status"]],
                                   [name, "Frequency range (GHz)", str(sample_record["frequency_range_ghz"])],
                                   [name, "RL minimum ties", len(points)], [name, "Maximum EAB thickness ties", len(sample_record["maximum_eab_details"])]])
                provenance.extend([[name, "Warning", warning] for warning in sample_record["warnings"]])
            except Exception as error:
                message = f"{type(error).__name__}: {error}"
                print(f"失败：{name}：{message}", file=sys.stderr)
                summaries.append({"sample": name, "status": "failed", "validation": "not_calculated", "error": message})
                member = {"sample": name, "status": "failed", "error": message, "member_directory": str(member_root)}
                failed_records = list(member_root.rglob("analysis_record.json")) if member_root.exists() else []
                if failed_records:
                    failed = json.loads(failed_records[0].read_text(encoding="utf-8"))
                    member["analysis_record"] = str(failed_records[0])
                    provenance.append([name, "Raw SHA-256", failed.get("raw_sha256", "unavailable")])
                provenance.extend([[name, "Raw file", entry["path"]], [name, "Failure", message]])
                if Path(entry["path"]).suffix.lower() == ".sdat":
                    try:
                        structure, table = inspect_sdat(entry["path"])
                        member_root.mkdir(parents=True, exist_ok=True)
                        table.to_csv(member_root/"sdat_uninterpreted_columns.csv", index=False)
                        (member_root/"sdat_structure.json").write_text(json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8")
                        member["sdat_diagnostic"] = str(member_root/"sdat_structure.json")
                    except Exception as diagnostic_error:
                        member["sdat_diagnostic_error"] = str(diagnostic_error)
            record["members"].append(member)
            save_batch_record(directory, record)
        run_lookup = dict(successful)
        record["comparison"] = compare_runs([(name, run_lookup[name]) for name in selected if name in run_lookup],
                                              directory/"comparison", style, options.get("curve_thickness", 2.))
        record["comparison"]["excluded_failed_samples"] = [name for name in selected if name not in {n for n, _ in successful}]
        provenance[0:0] = [["Batch", "Analysis date", record["analysis_date"]], ["Batch", "Software version", __version__],
                            ["Batch", "Git commit", record["git"]["commit"]], ["Batch", "Git dirty", record["git"]["dirty"]],
                            ["Batch", "Analysis configuration", json.dumps(options, ensure_ascii=False)],
                            ["Batch", "Summary tie policy", "Summary shows first tie; RL_minima and EAB_bands preserve all ties."],
                            ["Batch", "Result type", "Snapshot of Python calculations, not an editable calculation workbook."],
                            ["Batch", "Validation", "Refer to per-sample records; commercial reference pending."]]
        provenance.extend([["Comparison", "Note", note] for note in record["comparison"].get("notes", [])])
        escape_formula_cells(pd.DataFrame(summaries)).to_csv(directory/"all_samples_summary.csv", index=False)
        export_batch_excel(directory/"all_samples_summary.xlsx", summaries, minima, bands, provenance)
        succeeded = len(successful)
        record.update({"status": "success" if succeeded == len(entries) else "partial_failure" if succeeded else "failed",
                       "success_count": succeeded, "failure_count": len(entries)-succeeded})
        record["summary_sha256"] = hashlib.sha256((directory/"all_samples_summary.xlsx").read_bytes()).hexdigest()
        save_batch_record(directory, record)
        print(f"批次结果：{directory}\n成功 {succeeded}，失败 {len(entries)-succeeded}；真实结果待验证。")
        return directory
    except Exception as error:
        record.update({"status": "failed", "batch_error": f"{type(error).__name__}: {error}"})
        save_batch_record(directory, record)
        plt.close("all")
        raise


def main():
    """命令行读取目录或 JSON 清单；部分失败返回退出码 2，整体失败返回 1。"""
    parser = argparse.ArgumentParser(description="批量计算与原始网格样品比较")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--directory")
    source.add_argument("--manifest")
    parser.add_argument("--imaginary-convention", choices=["loss", "signed"], help="目录模式必须显式提供")
    parser.add_argument("--output", default="output")
    parser.add_argument("--compare", nargs="+", help="只比较列出的样品，其余仍分析")
    parser.add_argument("--dpi", type=int, default=600)
    parser.add_argument("--reuse", action="store_true", help="复用源 SHA-256 与配置相同的已完成运行")
    args = parser.parse_args()
    try:
        if args.manifest:
            if args.imaginary_convention:
                raise ValueError("清单模式请在 parser_defaults 中配置虚部约定。")
            entries, options, selected = load_manifest(args.manifest)
            skipped = []
        else:
            if args.imaginary_convention is None:
                raise ValueError("目录模式必须显式指定 --imaginary-convention。")
            entries, skipped = discover_samples(args.directory, {"imaginary_convention": args.imaginary_convention}, [args.output])
            options, selected = {}, None
        directory = analyze_batch(entries, output=args.output, analysis_options=options, compare_samples=args.compare or selected,
                                   style=PlotStyle(dpi=args.dpi), source=args.manifest or args.directory, skipped=skipped,
                                   reuse=args.reuse)
        status = json.loads((directory/"batch_record.json").read_text(encoding="utf-8"))["status"]
        return {"success": 0, "partial_failure": 2, "failed": 1}[status]
    except Exception as error:
        print(f"批量分析失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
