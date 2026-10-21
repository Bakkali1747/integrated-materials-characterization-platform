"""无量纲阻抗图与 RL 并排对照，标出模长范围但不宣称完整匹配。"""

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import Normalize
from matplotlib.figure import Figure

from export.origin_export import attach_grid
from plotting.rl_plot import rl_normalization
from plotting.style import PlotStyle, new_axes


def draw_impedance_map(ax, result, style, tolerance):
    """输入坐标轴、结果及模长容差；绘制 |z| 图，返回实际 mappable。

    1±tolerance 是可调显示范围，不是物理判据。粗黑线为 |z|=1，虚线为范围边界。
    """
    if not np.isfinite(tolerance) or not 0 < tolerance < 1:
        raise ValueError("阻抗模长显示容差必须在 0 与 1 之间。")
    values = np.abs(result.normalized_impedance)
    low, high = float(values.min()), float(values.max())
    norm = Normalize(low, high if high > low else low + 0.5)
    f, d = result.frequency_ghz, result.thickness_mm
    attach_grid(ax, f, d, values, "|Zin/Z0| (dimensionless)")
    if len(d) > 1:
        artist = ax.contourf(f, d, values, levels=np.linspace(norm.vmin, norm.vmax, 65), cmap=style.cmap, norm=norm)
        for level in (1-tolerance, 1., 1+tolerance):
            if low < level < high:
                contours = ax.contour(f, d, values, levels=[level], colors="black",
                                      linewidths=1. if level == 1 else .6,
                                      linestyles="solid" if level == 1 else "dashed")
                ax.clabel(contours, fmt="%.2g", fontsize=8)
    else:
        artist = ax.pcolormesh(f, d, values, shading="nearest", cmap=style.cmap, norm=norm)
    ax.set(xlabel="Frequency (GHz)", ylabel="Thickness (mm)",
           title=f"Modulus only: 1 ± {tolerance:g}")
    return artist


def plot_impedance_2d(result, style=None, tolerance=.1):
    """输入扫描结果；返回独立阻抗模长图及 mappable，颜色来自真实 |z| 矩阵。"""
    style = style or PlotStyle()
    fig, ax = new_axes(style)
    artist = draw_impedance_map(ax, result, style, tolerance)
    fig.colorbar(artist, ax=ax, label=r"$|Z_{in}/Z_0|$")
    return fig, artist


def plot_impedance_curve(result, style=None, tolerance=.1):
    """输入指定厚度结果；返回 |z|、Re(z)、Im(z) 频率曲线，均无量纲。"""
    style = style or PlotStyle()
    fig, ax = new_axes(style)
    z = result.normalized_impedance[0]
    for values, label in ((abs(z), "|z|"), (z.real, "Re(z)"), (z.imag, "Im(z)")):
        ax.plot(result.frequency_ghz, values, label=label, linewidth=style.linewidth)
    ax.axhspan(1-tolerance, 1+tolerance, alpha=.12, color="gray", label="|z| display band")
    ax.axhline(1, color="0.3", linewidth=.7, linestyle="--")
    ax.axhline(0, color="0.6", linewidth=.7, linestyle=":")
    ax.set(xlabel="Frequency (GHz)", ylabel="Normalized impedance z",
           title=f"d = {result.thickness_mm[0]:g} mm; full match: z = 1 + j0")
    ax.legend(frameon=False, fontsize=9)
    return fig


def plot_rl_impedance(result, style=None, tolerance=.1):
    """输入扫描结果；返回同一坐标范围的 RL / |z| 并排图，两侧各用自己的色标。"""
    style = style or PlotStyle()
    fig = Figure(figsize=(style.width*2, style.height), layout="constrained")
    FigureCanvasAgg(fig)
    axes = fig.subplots(1, 2, sharex=True, sharey=True)
    norm = rl_normalization(result.rl_db)
    attach_grid(axes[0], result.frequency_ghz, result.thickness_mm, result.rl_db, "RL (dB)")
    if len(result.thickness_mm) > 1:
        left = axes[0].contourf(result.frequency_ghz, result.thickness_mm, result.rl_db,
                                levels=np.linspace(norm.vmin, norm.vmax, 65), norm=norm, cmap=style.cmap)
    else:
        left = axes[0].pcolormesh(result.frequency_ghz, result.thickness_mm, result.rl_db,
                                  shading="nearest", norm=norm, cmap=style.cmap)
    axes[0].set(xlabel="Frequency (GHz)", ylabel="Thickness (mm)", title="RL")
    fig.colorbar(left, ax=axes[0], label="RL (dB)")
    right = draw_impedance_map(axes[1], result, style, tolerance)
    fig.colorbar(right, ax=axes[1], label=r"$|Z_{in}/Z_0|$")
    return fig
