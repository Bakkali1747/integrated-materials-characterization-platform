"""S 参数和 R/T/A 图始终显示候选 schema 状态，保持原始频率点。"""

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
