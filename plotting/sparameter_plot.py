"""S 参数和 R/T/A 图始终显示候选 schema 状态，保持原始频率点。"""

import numpy as np
from matplotlib.patches import Circle

from core.sparameter_mapping import S_NAMES
from plotting.style import PlotStyle, new_axes


def plot_sparameter_quantity(table, quantity="db", style=None, names=None):
    """输入逐点结果表和 magnitude/db/phase_deg；返回四条命名 S 曲线。"""
    labels = {"magnitude": "S-parameter magnitude", "db": "20 log10 |S| (dB)", "phase_deg": "Principal phase (deg)", "real_imag": "Complex S (real / imag)"}
    style = style or PlotStyle()
    fig, ax = new_axes(style)
    for name in (S_NAMES if names is None else names):
        if name not in S_NAMES:
            raise ValueError("未知 S 参数名称。")
        for component in (["real", "imag"] if quantity == "real_imag" else [quantity]):
            ax.plot(table.frequency_ghz, table[f"{name}_{component}"], label=f"{name} {component}", linewidth=style.linewidth,
                    linestyle="--" if component == "imag" else "-")
    ax.set(xlabel="Frequency (GHz)", ylabel=labels[quantity])
    ax.legend(frameon=False)
    return fig


def plot_rta(table, style=None):
    """输入逐点表；返回无量纲 R/T/A 曲线，不限制 y 轴以隐藏负值。"""
    style = style or PlotStyle()
    fig, ax = new_axes(style)
    for name in ("R", "T", "A"):
        ax.plot(table.frequency_ghz, table[name], label=name, linewidth=style.linewidth)
    ax.set(xlabel="Frequency (GHz)", ylabel="Power fraction (assumed normalization)")
    ax.legend(frameon=False)
    return fig


def plot_shielding_effectiveness(table, style=None):
    """输入逐点表；返回 SE_R / SE_A / SE_T 曲线，未定义点断线。"""
    style = style or PlotStyle()
    fig, ax = new_axes(style)
    for column, label in (("SE_R_db", "SE_R"), ("SE_A_db", "SE_A"), ("SE_T_db", "SE_T")):
        values = np.asarray(table[column], dtype=float)
        ax.plot(table.frequency_ghz, np.where(np.isfinite(values), values, np.nan),
                label=label, linewidth=style.linewidth)
    ax.set(xlabel="Frequency (GHz)", ylabel="Shielding effectiveness (dB)",
           title="Shielding effectiveness (power-wave assumption)")
    ax.legend(frameon=False)
    return fig


def plot_smith(table, style=None):
    """输入逐点表；在归一化反射系数平面上绘制 S11/S22 轨迹与 Smith 网格。"""
    style = style or PlotStyle()
    fig, ax = new_axes(style)
    theta = np.linspace(0, 2*np.pi, 361)
    ax.plot(np.cos(theta), np.sin(theta), color="0.4", linewidth=.8)
    for resistance in (0, .2, .5, 1, 2, 5):
        ax.add_patch(Circle((resistance/(1+resistance), 0), 1/(1+resistance),
                            fill=False, color="0.8", linewidth=.6))
    for reactance in (.2, .5, 1, 2, 5):
        for sign in (1, -1):
            ax.add_patch(Circle((1, 1/(sign*reactance)), 1/reactance,
                                fill=False, color="0.9", linewidth=.5))
    ax.axhline(0, color="0.5", linewidth=.6)
    for name, color in (("S11", "#1f77b4"), ("S22", "#d95f02")):
        gamma = (table[f"{name}_real"].to_numpy(dtype=float)
                 + 1j*table[f"{name}_imag"].to_numpy(dtype=float))
        if not len(gamma):
            continue
        ax.plot(gamma.real, gamma.imag, color=color, linewidth=style.linewidth, label=name)
        ax.scatter([gamma.real[0], gamma.real[-1]], [gamma.imag[0], gamma.imag[-1]],
                   color=color, s=20, zorder=3)
    ax.set_aspect("equal")
    ax.set_xlim(-1.05, 1.05)
    ax.set_ylim(-1.05, 1.05)
    ax.set(xlabel=r"Re($\Gamma$)", ylabel=r"Im($\Gamma$)", title="Smith chart (normalized reflection coefficient)")
    ax.legend(frameon=False, loc="upper right")
    return fig
