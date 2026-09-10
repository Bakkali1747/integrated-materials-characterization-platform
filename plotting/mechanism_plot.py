"""只绘制数据与模型对照，不输出弛豫次数、界面极化或涡流主导结论。"""

import numpy as np
from plotting.style import PlotStyle, new_axes
from plotting.rl_plot import plot_rl_2d


def plot_loss_tangents(table, style=None, component=None):
    """输入派生表；返回两种无量纲损耗角正切随 GHz 频率的曲线。"""
    style = style or PlotStyle()
    fig, ax = new_axes(style)
    for col, label in (("tan_delta_eps", r"$\tan\delta_\varepsilon$"), ("tan_delta_mu", r"$\tan\delta_\mu$")):
        if component is not None and col != component:
            continue
        ax.plot(table.frequency_ghz, table[col], label=label, linewidth=style.linewidth)
    ax.set(xlabel="Frequency (GHz)", ylabel="Loss tangent")
    ax.legend(frameon=False)
    return fig


def plot_scalar_parameter(table, column, style=None):
    """输入派生表和 alpha_per_m / c0_seconds；返回有明确 SI 单位的频率曲线。"""
    labels = {"alpha_per_m": r"$\alpha$ (m$^{-1}$)", "c0_seconds": r"$C_0$ (s)"}
    style = style or PlotStyle()
    fig, ax = new_axes(style)
    ax.plot(table.frequency_ghz, table[column], linewidth=style.linewidth)
    ax.set(xlabel="Frequency (GHz)", ylabel=labels[column])
    if column == "c0_seconds":
        ax.set_title("Auxiliary evidence only", fontsize=10)
        ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0), useMathText=True)
    return fig


def plot_cole_cole(table, style=None):
    """输入参数表；按频率顺序绘制 ε″ vs ε′，不拟合、不计数弛豫过程。"""
    style = style or PlotStyle()
    fig, ax = new_axes(style)
    ax.plot(table.eps_real, table.eps_imag, linewidth=style.linewidth)
    ax.set(xlabel=r"$\varepsilon'$", ylabel=r"$\varepsilon''$", title="Cole-Cole data; no mechanism assignment")
    ax.set_aspect("equal", adjustable="datalim")
    return fig


def plot_quarter_wave(table, comparison, orders=(1,), style=None):
    """输入理论表和实际极小值对照行；返回频率-厚度图，区分估算线与网格极小值。"""
    style = style or PlotStyle()
    fig, ax = new_axes(style)
    for order in orders:
        ax.plot(table.frequency_ghz, table[f"quarter_wave_n{order}_mm"],
                label=f"Quarter-wave estimate n={order}", linewidth=style.linewidth)
    ax.scatter([r["frequency_ghz"] for r in comparison], [r["actual_thickness_mm"] for r in comparison],
               s=5, color="black", alpha=.5, label="RL minimum at each scanned thickness")
    ax.set(xlabel="Frequency (GHz)", ylabel="Thickness (mm)")
    ax.legend(frameon=False, fontsize=8)
    return fig


def plot_quarter_wave_overlay(result, table, comparison, orders=(1,), style=None):
    """输入 RL 与理论表；返回叠加理论厚度线的 RL 图，不外推、保持扫描坐标范围。"""
    style = style or PlotStyle()
    fig, artist = plot_rl_2d(result, style)
    ax = fig.axes[0]
    limits = ax.get_ylim()
    for index, order in enumerate(orders):
        values = table[f"quarter_wave_n{order}_mm"]
        finite = values[np.isfinite(values)]
        outside = not len(finite) or finite.min() > limits[1] or finite.max() < limits[0]
        label = f"Quarter-wave n={order}" + (" (outside scan)" if outside else "")
        ax.plot(table.frequency_ghz, table[f"quarter_wave_n{order}_mm"], linestyle="--", linewidth=style.linewidth,
                color=("white", "orange", "cyan")[index % 3], label=label)
    ax.scatter([r["frequency_ghz"] for r in comparison], [r["actual_thickness_mm"] for r in comparison],
               s=4, color="white", label="RL minima by thickness")
    ax.set_ylim(limits)
    ax.legend(frameon=True, fontsize=8, facecolor="0.2", labelcolor="white", framealpha=.85)
    return fig
