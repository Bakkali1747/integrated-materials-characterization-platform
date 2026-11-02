"""样品比较编排：调用原分析、汇总、比较和 Excel API，不实现指标公式。"""
import logging
import uuid
from dataclasses import replace
from datetime import datetime

import pandas as pd

from core import __version__
from export.csv_safety import escape_formula_cells
from export.excel_export import export_batch_excel
from export.provenance import artifact_hashes, git_state
from gui.controllers.analysis_controller import Cancelled, analyze_request
from plotting.style import PlotStyle
from run_batch import compare_runs, save_batch_record, summarize_sample


def comparison_hashes(directory):
    """报告自身不能进入其产物哈希，避免写回后自引用失效。"""
    return {path: digest for path, digest in artifact_hashes(directory).items() if path not in {"batch_record.json", "batch_record.txt"}}


def compare_requests(requests, output, progress, cancelled, dpi=600):
    """输入明确勾选样品及共同配置；保存独立运行、十项图、汇总和全部并列明细。

    扫描网格、频率裁选与阈值必须一致；各样品可保留自身曲线厚度（不同厚度允许比较，
    结果按各自记录标注），不插值、不把不同厚度当成同条件排名。
    """
    if not requests or len({r.name for r in requests}) != len(requests):
        raise ValueError("请选择样品并为每个样品使用唯一名称。")
    if len({(r.thickness_min, r.thickness_max, r.thickness_step, r.frequency_min, r.frequency_max, r.threshold) for r in requests}) != 1:
        raise ValueError("比较必须使用相同扫描配置；不同原始频率网格可保留并单独提示。")
    directory = output / "comparisons" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:10])
    directory.mkdir(parents=True)
    record = {"software_version": __version__, "git": git_state(), "status": "started", "members": [],
              "interpolation": "OFF", "analysis_date": datetime.now().astimezone().isoformat()}
    figures, runs, summaries, minima, bands, provenance = {}, [], [], [], [], []
    save_batch_record(directory, record)
    try:
        for index, request in enumerate(requests):
            if cancelled():
                raise Cancelled("比较已取消；已完成的样品结果保留。")
            progress(int(index * 70 / len(requests)), f"分析 {request.name}")
            try:
                result = analyze_request(replace(request, output=directory / "samples", full_science=True, dpi=dpi),
                    lambda value, text: progress(int((index + value / 100) * 70 / len(requests)), text), cancelled)
                summary, points, eab, source = summarize_sample(request.name, result["directory"])
                runs.append((request.name, result["directory"]))
                summaries.append(summary); minima.extend(points); bands.extend(eab)
                provenance += [[request.name, "Raw file", source["raw_file"]], [request.name, "Raw SHA256", source["raw_sha256"]],
                               [request.name, "Validation", source["validation_status"]], [request.name, "Run", str(result["directory"])]]
                record["members"].append({"sample": request.name, "status": "success", "run_directory": str(result["directory"])})
                del result
            except Cancelled:
                raise
            except Exception as error:
                logging.getLogger("microwave.gui").exception("比较成员失败：%s", request.name)
                summaries.append({"sample": request.name, "status": "failed", "error": str(error), "validation": "not_calculated"})
                record["members"].append({"sample": request.name, "status": "failed", "error": str(error)})
            save_batch_record(directory, record)
        if cancelled():
            raise Cancelled("比较已取消，已完成样品保留。")

        def collect(key, fig):
            figures[key] = fig
            if cancelled():
                raise Cancelled("比较已取消，已输出的图保留。")
            progress(70 + len(figures) * 2, f"十项比较：{key}")
        record["comparison"] = compare_runs(runs, directory / "figures", PlotStyle(dpi=dpi), figure_callback=collect)
        escape_formula_cells(pd.DataFrame(summaries)).to_csv(directory / "summary.csv", index=False)
        export_batch_excel(directory / "summary.xlsx", summaries, minima, bands, provenance + [["Comparison", "Note", n] for n in record["comparison"].get("notes", [])])
        record.update(status="success" if len(runs) == len(requests) else "partial_failure" if runs else "failed",
                      success_count=len(runs), failure_count=len(requests)-len(runs), artifacts_sha256=comparison_hashes(directory))
        save_batch_record(directory, record)
        progress(100, "比较完成")
        comparison = record.get("comparison") or {}
        return {"directory": directory, "record": record, "figures": figures, "summaries": summaries, "minima": minima,
                "bands": bands, "curve_thickness": comparison.get("curve_thickness_mm"),
                "curve_thicknesses": comparison.get("curve_thickness_mm_per_sample", {})}
    except Exception as error:
        from plotting.style import plt
        for fig in figures.values():
            plt.close(fig)
        record.update(status="cancelled" if isinstance(error, Cancelled) else "failed", error=str(error), artifacts_sha256=comparison_hashes(directory))
        save_batch_record(directory, record)
        raise
