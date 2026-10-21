"""S 参数 GUI 适配；复用已验证的软件计算路径，候选状态不升级。"""
import json

import pandas as pd

from core.sparameter_mapping import load_sparameter_mapping
from export.origin_export import save_figure_bundle
from export.provenance import artifact_hashes, figure_provenance
from gui.controllers.analysis_controller import Cancelled
from plotting.sparameter_plot import plot_rta, plot_shielding_effectiveness, plot_smith, plot_sparameter_quantity
from plotting.style import PlotStyle, plt
from run_sparameters import analyze_sparameter_file, write_sparameter_record


def s_figure(result, quantity, channel="全部", dpi=600):
    """根据已计算结果选择通道/显示形式，仅调用 plotting。"""
    style = PlotStyle(dpi=dpi)
    if quantity == "RTA":
        fig = plot_rta(result["table"], style)
    elif quantity == "SE":
        fig = plot_shielding_effectiveness(result["table"], style)
    elif quantity == "smith":
        fig = plot_smith(result["table"], style)
    else:
        fig = plot_sparameter_quantity(result["table"], quantity, style,
                                       None if channel == "全部" else [channel])
    fig.suptitle(result["record"]["schema_status"] + " / NOT manufacturer-confirmed", fontsize=9)
    plt.close(fig)
    return fig


def analyze_s_request(path, name, output, schema, progress, cancelled, dpi=600):
    """调用正式 S 文件分析入口，保存元数据、QC 与 GUI 图；取消保留产物。"""
    if cancelled():
        raise Cancelled("已取消")
    progress(5, "解析 S 参数与物理一致性筛查")
    directory = analyze_sparameter_file(path, name=name, output=output,
        mapping=load_sparameter_mapping(schema) if schema else None, schema_file=schema or None,
        make_figures=False, style=PlotStyle(dpi=dpi))
    record = json.loads((directory / "analysis_record.json").read_text(encoding="utf-8"))
    result = {"directory": directory, "record": record,
              "table": pd.read_csv(directory / "sparameters_by_frequency.csv"), "figures": {}}
    try:
        record.update(entry_point="gui_phase2", status="rendering", parser_version=record["source"].get("parser", "sdat-v1"))
        write_sparameter_record(directory, record)
        folder = directory / "figures"
        folder.mkdir(exist_ok=True)
        provenance = figure_provenance(record, dpi=dpi)
        for i, quantity in enumerate(("magnitude", "db", "real_imag", "phase_deg", "RTA", "SE", "smith")):
            if cancelled():
                raise Cancelled("S 参数任务已取消；已写入产物保留。")
            progress(30 + i * 13, f"绘制 {quantity}")
            fig = s_figure(result, quantity, dpi=dpi)
            result["figures"][quantity] = fig
            save_figure_bundle(fig, folder / f"{quantity}.png", dpi=dpi, provenance=provenance)
        record.update(status="success", artifacts_sha256=artifact_hashes(directory))
        write_sparameter_record(directory, record)
        progress(100, "S 参数分析完成，schema 仍为候选")
        return result
    except Exception as error:
        record.update(status="cancelled" if isinstance(error, Cancelled) else "failed", error=str(error),
                      artifacts_sha256=artifact_hashes(directory))
        write_sparameter_record(directory, record)
        raise


def theory_comparison(theory, measured, progress, cancelled, dpi=600):
    """保存独立对照图和两份来源记录；不修改任一原分析目录。"""
    import uuid
    from datetime import datetime

    from core import __version__
    from export.provenance import git_state, json_safe
    from plotting.theory_measured import CAUTION, plot_theory_measured
    if cancelled():
        raise Cancelled("对照已取消")
    directory = measured["directory"].parent / ("theory_comparison_" + uuid.uuid4().hex[:12])
    directory.mkdir()
    record = {"analysis_date": datetime.now().astimezone().isoformat(), "software_version": __version__, "git": git_state(),
              "theory_run": str(theory["directory"]), "measured_run": str(measured["directory"]),
              "theory_raw_sha256": theory["record"]["raw_sha256"], "measured_raw_sha256": measured["record"]["raw_sha256"],
              "curve_thickness_mm": float(theory["curve"].thickness_mm[0]),
              "theory_validation": theory["record"]["validation_status"], "schema_status": measured["record"]["schema_status"],
              "interpolation": "OFF", "conditions_equivalence": "unconfirmed", "caution": CAUTION, "status": "started"}
    record_path = directory / "comparison_record.json"
    try:
        progress(30, "绘制明确来源的理论 / 实测对照")
        fig = plot_theory_measured(theory["curve"], measured["table"], PlotStyle(dpi=dpi))
        fig.suptitle("PENDING / candidate mapping", fontsize=10)
        plt.close(fig)
        save_figure_bundle(fig, directory / "theory_measured.png", dpi=dpi,
                           provenance=figure_provenance(record, dpi=dpi,
                               extra={"theory_run": str(theory["directory"]),
                                      "measured_run": str(measured["directory"])}))
        if cancelled():
            raise Cancelled("对照已取消，已输出图保留")
        record.update(status="success", artifacts_sha256=artifact_hashes(directory))
        record_path.write_text(json.dumps(json_safe(record), ensure_ascii=False, indent=2), encoding="utf-8")
        progress(100, "对照图与两份来源已保存")
        return fig, directory
    except Exception as error:
        record.update(status="cancelled" if isinstance(error, Cancelled) else "failed", error=str(error))
        record_path.write_text(json.dumps(json_safe(record), ensure_ascii=False, indent=2), encoding="utf-8")
        raise
