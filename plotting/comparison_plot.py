"""跨样品曲线只使用原生采样点；不构造共同频率网格，不插值。"""

from plotting.style import PlotStyle, new_axes, plt

PARAMETERS = {
    "eps_real": r"$\varepsilon'$", "eps_imag": r"$\varepsilon''$",
    "mu_real": r"$\mu'$", "mu_imag": r"$\mu''$",
    "tan_delta_eps": r"$\tan\delta_\varepsilon$", "tan_delta_mu": r"$\tan\delta_\mu$",
    "alpha_per_m": r"$\alpha$ (m$^{-1}$)", "c0_seconds": r"$C_0$ (s)",
    "rl_db": "RL (dB)", "eab_minus10_db_ghz": "EAB at -10 dB (GHz)"}


def plot_comparison(series, metric, style=None, curve_thickness=2.):
    """输入 name/x/y 系列、指标名；返回比较图，保留每个样品的独立 x 数组。

    RL 比较固定在同一指定厚度，EAB 比较横轴为厚度；其余横轴为 GHz。
    """
    style = style or PlotStyle()
    fig, ax = new_axes(style)
    colors = plt.get_cmap("tab10")
    for index, item in enumerate(series):
        ax.plot(item["x"], item["y"], label=item["name"], linewidth=style.linewidth,
                color=colors(index % 10), linestyle=("-", "--", ":", "-.")[(index//10) % 4])
    ax.set(xlabel="Thickness (mm)" if metric == "eab_minus10_db_ghz" else "Frequency (GHz)", ylabel=PARAMETERS[metric])
    if metric == "rl_db":
        ax.set_title(f"Common thickness: {curve_thickness:g} mm", fontsize=10)
    if metric == "c0_seconds":
        ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0), useMathText=True)
    # 图例放外侧，避免多样品遮住曲线；图片随图例扩展保存。
    ax.legend(frameon=False, fontsize=9, loc="upper left", bbox_to_anchor=(1.01, 1))
    return fig
