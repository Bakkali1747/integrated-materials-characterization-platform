"""Phase 2 结果组织：核心计算仍在 core，绘图仍在 plotting。"""

import numpy as np
import pandas as pd

from core.impedance import impedance_at_minima
from core.mechanism import mechanism_parameters, quarter_wave_minima_comparison
from plotting.impedance_plot import plot_impedance_2d, plot_impedance_curve, plot_rl_impedance
from plotting.mechanism_plot import (
    plot_cole_cole,
    plot_loss_tangents,
    plot_quarter_wave,
    plot_quarter_wave_overlay,
    plot_scalar_parameter,
)

NOTES = [
    "[COMMON] |Zin/Z0|≈1 仅表示模长接近 1；完整匹配还需要 Re(z)≈1、Im(z)≈0。",
    "[COMMON] C0 曲线只能作为磁损耗机制的辅助证据，不能单独证明涡流损耗机制。",
    "[COMMON] Cole-Cole 图只展示数据，不自动识别弛豫数量或判断界面极化。",
    "[COMMON] 四分之一波长厚度为模型估算，不保证对应有损材料 RL 极小值。",
    "[COMMON] α 使用常用非负公式；负损耗输入时不能将非负输出视为被动性的证据。",
]


def export_phase2(sample, result, curve, directory, save, style, orders=(1,), tolerance=.1, render_figures=True):
    """输入样品、RL/指定厚度结果、目录和图片保存函数；输出 Phase 2 摘要。

    保存 SI 制派生参数、完整复阻抗矩阵及理论厚度对照，警告追加到样品记录。
    """
    table, warnings = mechanism_parameters(sample, orders)
    sample.warnings.extend(warnings)
    comparison = quarter_wave_minima_comparison(result, table, orders)
    table.to_csv(directory / "loss_parameters.csv", index=False)
    pd.DataFrame(comparison).to_csv(directory / "quarter_wave_comparison.csv", index=False)
    z = result.normalized_impedance
    for name, values in (("abs", abs(z)), ("real", z.real), ("imag", z.imag)):
        frame = pd.DataFrame(values, columns=result.frequency_ghz)
        frame.insert(0, "thickness_mm", result.thickness_mm)
        frame.to_csv(directory / f"impedance_{name}_matrix.csv", index=False)
    zcurve = curve.normalized_impedance[0]
    pd.DataFrame({"frequency_ghz": curve.frequency_ghz, "thickness_mm": curve.thickness_mm[0],
                  "z_real": zcurve.real, "z_imag": zcurve.imag, "z_abs": abs(zcurve)}).to_csv(directory / "impedance_curve.csv", index=False)
    (directory / "mechanism_notes.txt").write_text("\n".join(NOTES) + "\n", encoding="utf-8")
    if render_figures:
        save(plot_loss_tangents(table, style), "loss_tangent.png")
        save(plot_scalar_parameter(table, "alpha_per_m", style), "attenuation.png")
        save(plot_scalar_parameter(table, "c0_seconds", style), "C0.png")
        save(plot_cole_cole(table, style), "Cole_Cole.png")
        save(plot_quarter_wave(table, comparison, orders, style), "quarter_wave.png")
        save(plot_impedance_curve(curve, style, tolerance), "impedance_curve.png")
        save(plot_impedance_2d(result, style, tolerance)[0], "impedance.png")
        if np.isfinite(result.rl_db).all():
            save(plot_rl_impedance(result, style, tolerance), "RL_impedance.png")
            save(plot_quarter_wave_overlay(result, table, comparison, orders, style), "RL_quarter_wave.png")
    return {"impedance_at_global_minima": impedance_at_minima(result),
            "impedance_modulus_display_tolerance": tolerance, "quarter_wave_orders": list(orders),
            "units": {"tan_delta_eps": "dimensionless", "tan_delta_mu": "dimensionless",
                      "alpha_per_m": "m^-1", "c0_seconds": "s", "quarter_wave_thickness": "mm", "z": "dimensionless"},
            "derived_undefined_counts": {col: int(table[col].isna().sum()) for col in table.columns[5:]},
            "notes": NOTES}
