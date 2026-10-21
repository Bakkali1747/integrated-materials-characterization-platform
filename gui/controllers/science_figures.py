"""图形目录与现有 plotting API 的适配；没有科学公式。"""
from plotting.em_parameters import plot_parameters
from plotting.impedance_plot import plot_impedance_2d, plot_impedance_curve, plot_rl_impedance
from plotting.mechanism_plot import (
    plot_cole_cole,
    plot_loss_tangents,
    plot_quarter_wave,
    plot_quarter_wave_overlay,
    plot_scalar_parameter,
)
from plotting.rl_plot import plot_rl_2d, plot_rl_3d, plot_rl_curve, plot_rl_multi_thickness

NAMES = {"permittivity": "ε′ / ε″", "permeability": "μ′ / μ″", "RL_curve": "指定厚度 RL 曲线",
         "RL_2D": "RL 二维图", "RL_3D": "RL 三维图", "loss_tangent": "介电 / 磁损耗角正切",
         "tan_delta_eps": "介电损耗角正切", "tan_delta_mu": "磁损耗角正切", "attenuation": "衰减常数 α",
         "C0": "C0 辅助参数", "Cole_Cole": "Cole–Cole", "quarter_wave": "四分之一波长估算",
         "impedance_curve": "指定厚度复阻抗", "impedance": "|Zin/Z0| 二维图",
         "RL_impedance": "RL / 阻抗对照", "RL_quarter_wave": "RL / 四分之一波长叠图"}
NAMES.update({"eps_real": "ε′ 比较", "eps_imag": "ε″ 比较", "mu_real": "μ′ 比较", "mu_imag": "μ″ 比较",
              "alpha_per_m": "α 比较", "c0_seconds": "C0 比较", "rl_db": "共同厚度 RL 比较",
              "eab_minus10_db_ghz": "EAB 随厚度比较"})
NAMES["RL_multi_thickness"] = "多厚度 RL 曲线（自动）"


def make_figure(completed, key, style):
    """输入已完成结果与图类型；调用正式绘图函数，重绘不重新计算。"""
    s, r, c = completed["sample"], completed["result"], completed["curve"]
    t = completed.get("science_table")
    q = completed.get("quarter_comparison")
    record = completed["record"]
    orders = tuple(record.get("phase2", {}).get("quarter_wave_orders", (1,)))
    builders = {
        "permittivity": lambda: plot_parameters(s, "permittivity", style),
        "permeability": lambda: plot_parameters(s, "permeability", style),
        "RL_curve": lambda: plot_rl_curve(c, style=style, threshold=record["rl_threshold_db"]),
        "RL_multi_thickness": lambda: plot_rl_multi_thickness(
            r, record["multi_thickness_rl"]["row_indices"], style, threshold=record["rl_threshold_db"]),
        "RL_2D": lambda: plot_rl_2d(r, style)[0], "RL_3D": lambda: plot_rl_3d(r, style)[0],
        "loss_tangent": lambda: plot_loss_tangents(t, style),
        "tan_delta_eps": lambda: plot_loss_tangents(t, style, "tan_delta_eps"),
        "tan_delta_mu": lambda: plot_loss_tangents(t, style, "tan_delta_mu"),
        "attenuation": lambda: plot_scalar_parameter(t, "alpha_per_m", style),
        "C0": lambda: plot_scalar_parameter(t, "c0_seconds", style),
        "Cole_Cole": lambda: plot_cole_cole(t, style),
        "quarter_wave": lambda: plot_quarter_wave(t, q, orders, style),
        "impedance_curve": lambda: plot_impedance_curve(c, style),
        "impedance": lambda: plot_impedance_2d(r, style)[0],
        "RL_impedance": lambda: plot_rl_impedance(r, style),
        "RL_quarter_wave": lambda: plot_quarter_wave_overlay(r, t, q, orders, style),
    }
    return builders[key]()
