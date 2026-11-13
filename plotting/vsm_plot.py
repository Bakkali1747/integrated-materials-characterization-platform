"""VSM 磁滞回线与背景扣除图；只使用已保存/已计算的数据，不重新计算指标。"""

from plotting.style import COLORBLIND, PlotStyle, new_axes


def _unit(metrics):
    return metrics.get("metrics_unit") or "emu"


def _mark_metrics(axes, metrics):
    unit = _unit(metrics)
    hc_positive = metrics.get("Hc_positive_oe")
    hc_negative = metrics.get("Hc_negative_oe")
    if hc_positive is not None:
        axes.plot([hc_positive], [0], marker="o", color=COLORBLIND[1], ms=5, ls="none",
                  label=f"Hc+ = {hc_positive:.6g} Oe")
    if hc_negative is not None:
        axes.plot([-hc_negative], [0], marker="o", color=COLORBLIND[1], ms=5, ls="none",
                  label=f"Hc- = {hc_negative:.6g} Oe")
    mr_positive = metrics.get("Mr_positive")
    mr_negative = metrics.get("Mr_negative")
    if mr_positive is not None:
        axes.plot([0], [mr_positive], marker="s", color=COLORBLIND[2], ms=4, ls="none",
                  label=f"Mr+ = {mr_positive:.6g} {unit}")
    if mr_negative is not None:
        axes.plot([0], [mr_negative], marker="s", color=COLORBLIND[2], ms=4, ls="none",
                  label=f"Mr- = {mr_negative:.6g} {unit}")


def plot_hysteresis(table, metrics, style=None, *, zoom=False):
    """输入标准表和指标；返回完整回线图或原点附近放大图。"""
    style = style or PlotStyle()
    figure, axes = new_axes(style)
    field = table["field_oe"].to_numpy(dtype=float)
    values = table["analysis_value"].to_numpy(dtype=float)
    axes.plot(field, values, color=COLORBLIND[0], lw=style.linewidth, label="measured loop")
    axes.axhline(0, color="#94A3B8", lw=.8)
    axes.axvline(0, color="#94A3B8", lw=.8)
    _mark_metrics(axes, metrics)
    axes.set_xlabel("H (Oe)")
    axes.set_ylabel(f"M ({_unit(metrics)})")
    if zoom:
        span = float(max(abs(field.min()), abs(field.max())))
        hc = metrics.get("Hc_oe") or span * .05
        half = max(5.0 * float(hc), span * .005)
        axes.set_xlim(-half, half)
        mr = metrics.get("Mr")
        ms = metrics.get("Ms")
        limit = max(5.0 * abs(mr), abs(ms) * .25) if mr is not None and ms is not None else None
        if limit:
            axes.set_ylim(-limit, limit)
        axes.set_title("Hysteresis loop near origin")
    else:
        axes.set_title("VSM hysteresis loop")
    axes.legend(loc="best", fontsize=max(7, style.font_size - 2), frameon=False)
    return figure


def plot_background(table, metrics, style=None):
    """原始磁矩、线性背景与扣除后磁矩；仅当运行使用线性背景时调用。"""
    style = style or PlotStyle()
    figure, axes = new_axes(style)
    field = table["field_oe"].to_numpy(dtype=float)
    raw = table["moment_emu"].to_numpy(dtype=float)
    corrected = table["corrected_moment_emu"].to_numpy(dtype=float)
    axes.plot(field, raw, color=COLORBLIND[3], lw=style.linewidth, ls="--", label="raw moment")
    axes.plot(field, corrected, color=COLORBLIND[0], lw=style.linewidth, label="background-corrected")
    background = (metrics.get("background") or {})
    if background.get("mode") == "linear_high_field":
        slope = background.get("slope_emu_per_oe")
        intercept = background.get("intercept_emu")
        if slope is not None and intercept is not None:
            axes.plot(field, slope * field + intercept, color=COLORBLIND[4], lw=1.1, ls=":",
                      label="linear high-field fit")
    axes.set_xlabel("H (Oe)")
    axes.set_ylabel("m (emu)")
    axes.set_title("VSM background subtraction")
    axes.legend(loc="best", fontsize=max(7, style.font_size - 2), frameon=False)
    return figure


def plot_hysteresis_overview(table, metrics, style=None):
    """返回 (完整回线, 原点放大)；两者共享同一数据表。"""
    return plot_hysteresis(table, metrics, style, zoom=False), \
        plot_hysteresis(table, metrics, style, zoom=True)


def make_vsm_figure(table, metrics, key, dpi=600):
    """按图类型创建 Figure；GUI 与 CLI 共用同一绘图实现。"""
    style = PlotStyle(dpi=dpi)
    if key == "hysteresis":
        return plot_hysteresis(table, metrics, style)
    if key == "hysteresis_zoom":
        return plot_hysteresis(table, metrics, style, zoom=True)
    if key == "background":
        if (metrics.get("background") or {}).get("mode") != "linear_high_field":
            raise ValueError("本次运行未启用背景扣除，没有背景图。")
        return plot_background(table, metrics, style)
    raise ValueError(f"未知 VSM 图类型：{key}")
