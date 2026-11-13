"""VSM GUI 适配；数值计算全部在 core.vsm_service，本层只绘图与保存。"""

from core.vsm import inspect_vsm_table
from core.vsm_service import VSMConfig, execute, load_completed_vsm_run, write_vsm_record
from export.origin_export import save_figure_bundle
from export.provenance import artifact_hashes, figure_provenance
from plotting.style import plt
from plotting.vsm_plot import make_vsm_figure

FIGURE_KEYS = ("hysteresis", "hysteresis_zoom", "background")


def vsm_figure(result, key, dpi=600):
    """输入已完成运行快照；返回单张图，不重新计算任何指标。"""
    return make_vsm_figure(result["table"], result["metrics"], key, dpi)


def _figure_keys(metrics):
    keys = ["hysteresis", "hysteresis_zoom"]
    if (metrics.get("background") or {}).get("mode") == "linear_high_field":
        keys.append("background")
    return keys


def analyze_vsm_request(config: VSMConfig, progress=lambda percent, text: None, cancelled=lambda: False):
    """执行 VSM 核心分析、保存图组，并返回 GUI 快照。"""
    result = execute(config, progress=progress, cancelled=cancelled, cancel_exception=Cancelled)
    figures = {}
    folder = result.directory / "figures"
    folder.mkdir()
    provenance = figure_provenance(result.record, dpi=config.dpi)
    for index, key in enumerate(_figure_keys(result.analysis)):
        if cancelled():
            raise Cancelled("VSM 绘图已取消；已保存产物保留。")
        progress(80 + index * 5, f"绘制 {key}")
        figure = vsm_figure({"table": result.table, "metrics": result.analysis}, key, config.dpi)
        figures[key] = figure
        save_figure_bundle(figure, folder / f"{key}.png", dpi=config.dpi, provenance=provenance)
        plt.close(figure)
    result.record.update(figure_output="saved", artifacts_sha256=artifact_hashes(result.directory))
    write_vsm_record(result.directory, result.record)
    progress(100, "VSM 分析完成")
    flat_metrics = {**result.analysis["metrics"], "background": result.analysis["background"],
                    "quality": result.analysis["quality"], "warnings": result.analysis["warnings"],
                    "status": result.analysis["status"], "note": result.analysis["note"]}
    return {"directory": result.directory, "record": result.record, "data": result.data,
            "table": result.table, "metrics": flat_metrics, "figures": figures}


class Cancelled(Exception):
    """协作式取消；只在阶段之间停止，不删除已保存数据。"""


def load_vsm_request(directory):
    """读取已登记 VSM 运行；图按需生成，不重新计算指标。"""
    saved = load_completed_vsm_run(directory)
    return {"directory": saved["directory"], "record": saved["record"],
            "table": saved["table"], "metrics": saved["metrics"],
            "figures": {key: None for key in _figure_keys(saved["metrics"])}}


def vsm_metrics_rows(metrics):
    """返回指标表的可显示行；单位取自运行记录，不推断。"""
    unit = metrics.get("metrics_unit") or "emu"
    labels = [("Hc", "Hc", "Oe"), ("Hc_am", "Hc", "A/m"),
              ("Hc_positive_oe", "Hc+", "Oe"), ("Hc_negative_oe", "Hc-", "Oe"),
              ("Mr", "Mr", unit), ("Mr_positive", "Mr+", unit), ("Mr_negative", "Mr-", unit),
              ("Ms", "Ms", unit), ("Ms_positive", "Ms+", unit), ("Ms_negative", "Ms-", unit),
              ("squareness", "Mr/Ms", "—"), ("loop_closure", "回线闭合差", unit),
              ("saturation_field_oe", "最大场", "Oe")]
    return [(label, metrics.get(key), unit_name) for key, label, unit_name in labels
            if metrics.get(key) is not None]


def vsm_summary_text(record, metrics):
    """生成界面摘要文本；缺失值明确写不可计算。"""
    unit = metrics.get("metrics_unit") or "emu"
    background = metrics.get("background") or {}
    source = record.get("source") or {}
    mass_source = {"dat_header": "DAT 文件头", "user": "用户输入"}.get(source.get("mass_source"), "未提供")
    instrument = source.get("instrument_metrics") or {}
    instrument_text = ""
    if instrument:
        instrument_text = ("；仪器内置（仅供核对）：" + "，".join(
            f"{key}={value}" for key, value in instrument.items() if key in ("Hci(Oe)", "Mr(emu)", "Ms(emu)")))
    lines = [
        f"样品：{record.get('sample')}",
        f"来源：{record.get('raw_file')}",
        f"磁场范围：{record.get('field_range_oe')} Oe；{record.get('field_points')} 点",
        f"质量归一化：{'是' if record.get('mass_normalization') else '否（仅磁矩）'}；来源：{mass_source}",
        f"背景扣除：{background.get('mode', 'none')}"
        + (f"（|H| ≥ {background.get('minimum_abs_field_oe'):g} Oe，R²={background.get('r_squared')}）"
           if background.get("mode") == "linear_high_field" else ""),
        f"Hc：{_fmt(metrics.get('Hc_oe'))} Oe / {_fmt(metrics.get('Hc_am'))} A/m",
        f"Mr：{_fmt(metrics.get('Mr'))} {unit}",
        f"Ms：{_fmt(metrics.get('Ms'))} {unit}",
        f"Mr/Ms：{_fmt(metrics.get('squareness'))}",
        f"状态：{record.get('status')}；验证：{record.get('validation_status')}" + instrument_text,
    ]
    warnings = list(record.get("warnings") or [])
    if warnings:
        lines += ["", "警告：", *warnings]
    lines += ["", "[COMMON] Hc/Mr 由离散点线性插值；Ms 取最大场处端值，不代表真实饱和。",
              "背景扣除与质量归一化是显式选项；未进行平滑、排序、裁剪或补值。"]
    return "\n".join(lines)


def _fmt(value):
    return "不可计算" if value is None else f"{float(value):.6g}"


def read_vsm_preview(path, *, sheet=0, header_row=0, encoding=None, delimiter=None):
    """读取原始表头和前几行，供界面选择列名；不做单位换算或科学分析。"""
    return inspect_vsm_table(path, sheet=sheet, header_row=header_row, encoding=encoding,
                             delimiter=delimiter)
