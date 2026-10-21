"""S 参数计算和一致性筛查；不依赖文件列顺序，不自动修正原数据。"""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from core.sparameter_mapping import S_NAMES


@dataclass
class SParameterTolerances:
    """可配置的无量纲筛查容差，不是厂商标准或充分的被动性证明。"""

    magnitude_atol: float = 1e-6
    energy_atol: float = 1e-6
    reciprocity_atol: float = .02
    reciprocity_rtol: float = .02

    def validate(self):
        """检查每个容差有限且非负，避免无效配置掩盖异常。"""
        for key, value in asdict(self).items():
            if isinstance(value, bool) or not np.isfinite(value) or value < 0:
                raise ValueError(f"{key} 必须为有限非负数。")


def correlation_or_none(left, right):
    """返回 Pearson 相关系数；少于两点或常数序列时返回 None，不伪造相关性。"""
    if len(left) < 2 or np.ptp(left) == 0 or np.ptp(right) == 0:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def analyze_sparameters(frequency_ghz, s_parameters, tolerances=None):
    """输入 GHz 频率与四组命名复数组；返回逐点表和 QC 报告。

    [COMMON] 幅度=|S|，dB=20log10|S|，相位为主值度数、不展开；零幅度的 dB=-inf，
    相位未定义为 NaN。R=|S11|²、T=|S21|²、A=1−R−T，始终保留负 A。
    功率解释以相容的功率波/端口归一化为前提；当前归一化仍待外部确认。
    """
    tolerances = tolerances or SParameterTolerances()
    tolerances.validate()
    f = np.asarray(frequency_ghz, dtype=float)
    if f.ndim != 1 or not len(f) or not np.isfinite(f).all() or np.any(f <= 0) or np.any(np.diff(f) <= 0):
        raise ValueError("频率必须是非空、有限、正值、递增的一维数组。")
    if set(s_parameters) != set(S_NAMES):
        raise ValueError("计算必须提供命名的 S11/S21/S12/S22；不接受匿名列位置。")
    table = pd.DataFrame({"frequency_ghz": f})
    arrays, warnings, counts = {}, [], {}
    for name in S_NAMES:
        values = np.asarray(s_parameters[name], dtype=complex)
        if values.shape != f.shape or not np.isfinite(values).all():
            raise ValueError(f"{name} 必须与频率等长且全部有限。")
        arrays[name] = values
        magnitude = np.abs(values)
        with np.errstate(divide="ignore"):
            db = 20*np.log10(magnitude)
        phase = np.angle(values, deg=True)
        phase[magnitude == 0] = np.nan
        table[f"{name}_real"], table[f"{name}_imag"] = values.real, values.imag
        table[f"{name}_complex"] = [str(value) for value in values]
        table[f"{name}_magnitude"], table[f"{name}_db"], table[f"{name}_phase_deg"] = magnitude, db, phase
        table[f"{name}_magnitude_exceeds_tolerance"] = magnitude > 1+tolerances.magnitude_atol
        counts[name] = int(table[f"{name}_magnitude_exceeds_tolerance"].sum())
        if counts[name]:
            warnings.append(f"[COMPUTED] {name} 有 {counts[name]} 点 |S| > 1 + magnitude_atol。")
        if np.any(magnitude == 0):
            warnings.append(f"[COMMON] {name} 有零幅度点；dB 保留 -inf，相位未定义保存为空值。")
    try:
        with np.errstate(over="raise", invalid="raise"):
            r = np.abs(arrays["S11"])**2
            t = np.abs(arrays["S21"])**2
            total = r+t
            absorption = 1-r-t
            difference = np.abs(arrays["S21"]-arrays["S12"])
    except FloatingPointError as error:
        raise ValueError("S 参数功率/互易性计算溢出，请检查输入数量级。") from error
    limit = tolerances.reciprocity_atol + tolerances.reciprocity_rtol*np.maximum(np.abs(arrays["S21"]), np.abs(arrays["S12"]))
    table["R"], table["T"], table["A"] = r, t, absorption
    table["R_plus_T"] = total
    with np.errstate(divide="ignore", invalid="ignore"):
        reflection_limit = 1 - r
        se_r = np.where(reflection_limit > 0, -10*np.log10(np.where(reflection_limit > 0, reflection_limit, 1)), np.nan)
        se_a = np.where((reflection_limit > 0) & (t > 0),
                        -10*np.log10(np.where((reflection_limit > 0) & (t > 0), t/reflection_limit, 1)), np.nan)
        se_t = -10*np.log10(t)
    table["SE_R_db"], table["SE_A_db"], table["SE_T_db"] = se_r, se_a, se_t
    table["SE_undefined"] = ~np.isfinite(se_r) | ~np.isfinite(se_a)
    table["energy_exceeds_tolerance"] = total > 1+tolerances.energy_atol
    table["A_negative"] = absorption < 0
    table["A_negative_exceeds_tolerance"] = absorption < -tolerances.energy_atol
    table["reciprocity_abs_difference"] = difference
    table["reciprocity_limit"] = limit
    table["reciprocity_exceeds_tolerance"] = difference > limit
    if table.A_negative.any():
        warnings.append(f"[COMPUTED] A 有 {int(table.A_negative.sum())} 个负值，包括容差内轻微负值；未 clip。")
    if table.energy_exceeds_tolerance.any():
        warnings.append(f"[COMPUTED] R+T 有 {int(table.energy_exceeds_tolerance.sum())} 点超过 1 + energy_atol。")
    if table.reciprocity_exceeds_tolerance.any():
        warnings.append(f"[COMPUTED] S21/S12 有 {int(table.reciprocity_exceeds_tolerance.sum())} 点超出设定互易性容差。")
    if table.SE_undefined.any():
        warnings.append(f"[COMMON] 屏蔽效能有 {int(table.SE_undefined.sum())} 点因 R≥1 或 T=0 无定义；"
                        "SE_R/SE_A 保留空值，SE_T 在 T=0 时为 +inf，不裁剪。")
    report = {"tolerances": asdict(tolerances), "magnitude_violation_counts": counts,
              "maximum_magnitudes": {name: float(table[f"{name}_magnitude"].max()) for name in S_NAMES},
              "energy_violation_count": int(table.energy_exceeds_tolerance.sum()),
              "negative_absorption_count": int(table.A_negative.sum()),
              "minimum_A": float(absorption.min()), "maximum_A": float(absorption.max()),
              "maximum_R_plus_T": float(total.max()),
              "se_undefined_count": int(table.SE_undefined.sum()),
              "maximum_SE_T_db": float(se_t[np.isfinite(se_t)].max()) if np.isfinite(se_t).any() else None,
              "se_definition": "SE_R=-10log10(1-R); SE_A=-10log10(T/(1-R)); SE_T=SE_R+SE_A=-10log10(T)",
              "reciprocity": {"real_correlation": correlation_or_none(arrays["S21"].real, arrays["S12"].real),
                              "imag_correlation": correlation_or_none(arrays["S21"].imag, arrays["S12"].imag),
                              "mean_absolute_complex_difference": float(difference.mean()), "max_absolute_complex_difference": float(difference.max()),
                              "violation_count": int(table.reciprocity_exceeds_tolerance.sum()),
                              "rule": "abs(S21-S12) <= atol + rtol*max(abs(S21),abs(S12))"},
              "warnings": warnings, "clipping": "OFF", "interpolation": "OFF", "phase_unwrap": "OFF",
              "power_normalization_status": "assumed_compatible_not_externally_confirmed",
              "interpretation": "Consistency screens only; neither prove full two-port passivity nor confirm manufacturer column order."}
    return table, report
