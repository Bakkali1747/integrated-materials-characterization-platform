"""按数据类型叠加多样品结果；只读取已完成运行，不重新计算指标。"""

import numpy as np

from plotting.style import COLORBLIND, PlotStyle, new_axes


def _colors(index):
    return COLORBLIND[index % len(COLORBLIND)]


def plot_vsm_comparison(runs, style=None):
    """归一化磁滞回线叠加，便于比较形状与矫顽场。"""
    style = style or PlotStyle()
    figure, axes = new_axes(style)
    for index, run in enumerate(runs):
        table = run["table"]
        field = table["field_oe"].to_numpy(dtype=float)
        values = table["analysis_value"].to_numpy(dtype=float)
        peak = float(np.max(np.abs(values))) if len(values) else 0.0
        if peak <= 0:
            continue
        axes.plot(field, values / peak, color=_colors(index), lw=style.linewidth,
                  label=f"{run['record'].get('sample', 'sample')}")
    axes.axhline(0, color="#94A3B8", lw=.8)
    axes.axvline(0, color="#94A3B8", lw=.8)
    axes.set_xlabel("H (Oe)")
    axes.set_ylabel("M / Mmax")
    axes.set_title("VSM normalized hysteresis loops")
    axes.legend(loc="best", fontsize=max(7, style.font_size - 2), frameon=False)
    return figure


def plot_xrd_comparison(runs, style=None):
    """归一化 XRD 图谱叠加；不改变原始强度与峰表。"""
    style = style or PlotStyle()
    figure, axes = new_axes(style)
    for index, run in enumerate(runs):
        table = run["table"]
        x = table["two_theta_deg"].to_numpy(dtype=float)
        values = table["intensity"].to_numpy(dtype=float)
        peak = float(np.max(values)) if len(values) else 0.0
        if peak <= 0:
            continue
        axes.plot(x, values / peak, color=_colors(index), lw=style.linewidth,
                  label=f"{run['record'].get('sample', 'sample')}")
    axes.set_xlabel("2θ (deg)")
    axes.set_ylabel("Normalized intensity")
    axes.set_title("XRD patterns (normalized)")
    axes.legend(loc="best", fontsize=max(7, style.font_size - 2), frameon=False)
    return figure


def plot_sparameter_comparison(runs, channel="S21", style=None):
    """叠加同一通道的 dB 曲线；各运行独立解析，不混合 schema。"""
    style = style or PlotStyle()
    figure, axes = new_axes(style)
    column = f"{channel}_db"
    for index, run in enumerate(runs):
        table = run["table"]
        if column not in table.columns:
            continue
        frequency = table["frequency_ghz"].to_numpy(dtype=float)
        values = table[column].to_numpy(dtype=float)
        axes.plot(frequency, values, color=_colors(index), lw=style.linewidth,
                  label=f"{run['record'].get('sample', 'sample')}")
    axes.set_xlabel("Frequency (GHz)")
    axes.set_ylabel(f"{channel} (dB)")
    axes.set_title(f"Measured {channel} comparison")
    axes.legend(loc="best", fontsize=max(7, style.font_size - 2), frameon=False)
    return figure
