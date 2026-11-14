"""XRD 图谱与参考相匹配图；只使用已保存表格与峰结果，不重新计算。"""

import numpy as np
from matplotlib.ticker import MaxNLocator

from plotting.style import COLORBLIND, PlotStyle, new_axes


def _peak_label(peak, index):
    if peak.get("d_angstrom"):
        return f"{peak['two_theta_deg']:.2f}° / d={peak['d_angstrom']:.3f} Å"
    return f"{peak['two_theta_deg']:.2f}°"


def plot_xrd_pattern(table, analysis, style=None, *, compact=False):
    """原始强度、背景与检测峰；compact 用于界面小画布，减少标注占用的高度。"""
    style = style or PlotStyle()
    figure, axes = new_axes(style)
    x = table["two_theta_deg"].to_numpy(dtype=float)
    raw = table["intensity"].to_numpy(dtype=float)
    axes.plot(x, raw, color="#475569", lw=style.linewidth, label="observed")
    background = analysis.get("background") or {}
    if background.get("mode") == "linear":
        axes.plot(x, table["background"].to_numpy(dtype=float), color=COLORBLIND[1], lw=1.0,
                  ls="--", label="linear background")
    peaks = analysis.get("peaks") or []
    if peaks:
        axes.plot([peak["two_theta_deg"] for peak in peaks],
                  [peak["intensity"] for peak in peaks], marker="v", ms=5, ls="none",
                  color=COLORBLIND[0], label="detected peaks")
        for index, peak in enumerate(peaks):
            label = f"{peak['two_theta_deg']:.2f}°" if compact else _peak_label(peak, index)
            axes.annotate(label, (peak["two_theta_deg"], peak["intensity"]),
                          textcoords="offset points", xytext=(2, 4),
                          fontsize=max(6, style.font_size - 4),
                          rotation=90, color=COLORBLIND[0])
    axes.set_xlabel("2θ (deg)")
    axes.set_ylabel("Intensity (counts)")
    axes.set_title("" if compact else "XRD pattern with detected peaks")
    axes.legend(loc="best", fontsize=max(7, style.font_size - 2), frameon=False)
    if compact:
        maximum = float(np.max(raw)) if len(raw) else 1.0
        axes.set_ylim(0, maximum * 1.03 if maximum > 0 else 1.0)
        axes.yaxis.set_major_locator(MaxNLocator(nbins=4))
        figure.set_layout_engine(None)
        figure.subplots_adjust(left=.11, right=.98, bottom=.21, top=.84)
    return figure


def plot_xrd_phase_matches(table, analysis, style=None):
    """观测峰与参考相棒图；分数是匹配筛查，不是物相鉴定。"""
    style = style or PlotStyle()
    figure, axes = new_axes(style)
    x = table["two_theta_deg"].to_numpy(dtype=float)
    raw = table["intensity"].to_numpy(dtype=float)
    axes.plot(x, raw, color="#94A3B8", lw=1.0, label="observed")
    matching = analysis.get("reference_matching") or []
    maximum = float(raw.max()) if len(raw) else 1.0
    for index, phase in enumerate(matching[:5]):
        matches = phase.get("matches") or []
        base = -0.08 * maximum * (index + 1)
        height = 0.06 * maximum
        axes.vlines([match["reference_2theta_deg"] for match in matches], base, base + height,
                    color=COLORBLIND[(index + 2) % len(COLORBLIND)],
                    label=f"{phase['phase']} (score {phase['score']:.2f})")
    axes.axhline(0, color="#CBD5E1", lw=.8)
    axes.set_xlabel("2θ (deg)")
    axes.set_ylabel("Intensity (counts)")
    axes.set_title("Reference phase peak matching")
    axes.legend(loc="best", fontsize=max(7, style.font_size - 2), frameon=False)
    return figure


def make_xrd_figure(table, analysis, key, dpi=600, *, compact=False):
    style = PlotStyle(dpi=dpi)
    if key == "xrd_pattern":
        return plot_xrd_pattern(table, analysis, style, compact=compact)
    if key == "xrd_phase_matches":
        if not analysis.get("reference_matching"):
            raise ValueError("本次运行没有参考相匹配结果。")
        return plot_xrd_phase_matches(table, analysis, style)
    raise ValueError(f"未知 XRD 图类型：{key}")
