"""理论/实测来源并列展示，不对齐网格、不宣称测量边界条件等价。"""
from plotting.style import PlotStyle, new_axes

CAUTION = "Interpret with caution: measured S11 and calculated metal-backed RL may represent different measurement conditions."


def plot_theory_measured(curve, measured, style=None):
    """输入已有理论 RLResult 与实测逐点表；原生频率分别作图，不计算新指标。"""
    style = style or PlotStyle()
    fig, ax = new_axes(style)
    ax.plot(curve.frequency_ghz, curve.rl_db[0], label=f"Calculated RL, d={curve.thickness_mm[0]:g} mm")
    ax.plot(measured.frequency_ghz, measured.S11_db, label="Measured S11", linestyle="--")
    ax.set(xlabel="Frequency (GHz)", ylabel="dB", title="Different measurement conditions may apply")
    ax.legend(frameon=False)
    return fig
