from plotting.style import PlotStyle, new_axes


def plot_parameters(sample, kind="permittivity", style=None):
    """输入样品与介电/磁导类别；返回频率曲线图，横轴 GHz、纵轴相对参数。"""
    style = style or PlotStyle()
    if kind not in ("permittivity", "permeability"):
        raise ValueError("kind 必须为 permittivity 或 permeability。")
    prefix, symbol = ("eps", r"\varepsilon") if kind == "permittivity" else ("mu", r"\mu")
    fig, ax = new_axes(style)
    for suffix, label in (("real", "'"), ("imag", "''")):
        ax.plot(sample.data.frequency_ghz, sample.data[f"{prefix}_{suffix}"],
                label=f"${symbol}{label}$", linewidth=style.linewidth)
    ax.set(xlabel="Frequency (GHz)", ylabel=f"Relative {kind}")
    ax.legend(frameon=False)
    return fig
