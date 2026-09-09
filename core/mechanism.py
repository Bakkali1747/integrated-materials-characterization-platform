"""[COMMON] 损耗辅助参数与四分之一波长估算；不自动推断材料机理。"""

import numpy as np
from core.electromagnetic import make_complex
from core.units import C, ghz_to_hz


def checked_parameters(frequency_hz, eps_complex, mu_complex):
    """输入 Hz 频率和无量纲相对复参数；返回等长有限一维数组，拒绝无效输入。"""
    f = np.asarray(frequency_hz, dtype=float)
    eps, mu = np.asarray(eps_complex, dtype=complex), np.asarray(mu_complex, dtype=complex)
    if f.ndim != 1 or not len(f) or eps.shape != f.shape or mu.shape != f.shape:
        raise ValueError("频率、ε、μ 必须为非空等长一维数组。")
    if not all(np.isfinite(x).all() for x in (f, eps, mu)) or np.any(f <= 0):
        raise ValueError("输入必须有限，频率必须 > 0 Hz。")
    return f, eps, mu


def loss_tangent(real, loss_imag):
    """输入实部及损耗系数；返回无量纲 loss_imag/real，形状不变。

    实部精确为零时返回 NaN，调用层必须记录警告；负值保留，不替换分母。
    """
    real, loss_imag = np.asarray(real, dtype=float), np.asarray(loss_imag, dtype=float)
    if real.shape != loss_imag.shape or not np.isfinite(real).all() or not np.isfinite(loss_imag).all():
        raise ValueError("损耗角输入必须有限且同形状。")
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        return np.divide(loss_imag, real, out=np.full_like(real, np.nan), where=real != 0)


def attenuation_constant(frequency_hz, eps_complex, mu_complex):
    """输入 Hz 频率及 ε′−jε″、μ′−jμ″；返回一维常用非负 α，单位 m^-1。

    [COMMON] A=μ″ε″−μ′ε′，B=μ′ε″+μ″ε′；α=√2πf/c * √(A+hypot(A,B))。
    A<0 时用 |B|/√(hypot(A,B)−A) 避免低损耗区相消。
    这个非负公式本身不判断被动性；负损耗输入必须由调用层提示。
    """
    f, eps, mu = checked_parameters(frequency_hz, eps_complex, mu_complex)
    er, ei, mr, mi = eps.real, -eps.imag, mu.real, -mu.imag
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            a = mi * ei - mr * er
            b = mr * ei + mi * er
            radius = np.hypot(a, b)
            root = np.empty_like(a)
            negative = a < 0
            root[negative] = np.abs(b[negative]) / np.sqrt(radius[negative] - a[negative])
            root[~negative] = np.sqrt(a[~negative] + radius[~negative])
            return np.sqrt(2) * np.pi * f / C * root
        except FloatingPointError as error:
            raise ValueError("α 计算溢出或无效，请核查参数数量级。") from error


def eddy_current_c0(frequency_hz, mu_real, mu_loss_imag):
    """输入频率 Hz 与相对磁参数；返回 C0=μ″/(μ′²f)，单位 s。

    μ′=0 返回 NaN 并由调用层警告；不以 C0 曲线自动证明涡流损耗。
    """
    f, _, mu = checked_parameters(frequency_hz, np.ones_like(frequency_hz), make_complex(mu_real, mu_loss_imag))
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        denominator = mu.real ** 2 * f
        values = np.divide(-mu.imag, denominator, out=np.full_like(f, np.nan), where=denominator != 0)
        values[~np.isfinite(denominator)] = np.nan
    return values


def quarter_wave_thickness(frequency_hz, eps_complex, mu_complex, order=1):
    """输入 Hz 频率、相对复参数和正奇数阶 n；返回一维估算厚度 m。

    [COMMON] tm=nc/[4f√(|εr||μr|)]。它是四分之一波长模型估算，
    并不保证对应有损材料的实际 RL 极小值。零参数返回 NaN，由调用层警告。
    """
    if isinstance(order, bool) or not isinstance(order, (int, np.integer)) or order < 1 or order % 2 != 1:
        raise ValueError("四分之一波长阶数必须为正奇数整数，例如 1、3、5。")
    f, eps, mu = checked_parameters(frequency_hz, eps_complex, mu_complex)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        denominator = 4 * f * np.sqrt(np.abs(eps)) * np.sqrt(np.abs(mu))
        result = np.divide(order*C, denominator, out=np.full_like(f, np.nan), where=denominator != 0)
        result[~np.isfinite(denominator)] = np.nan
    return result


def mechanism_parameters(sample, orders=(1,)):
    """输入标准化样品和阶数；返回含派生列的数据表及警告列表，不改原始表。

    tanδ 无量纲，α 为 m^-1，C0 为 s，理论厚度展示为 mm。
    派生量奇异点明确保留 NaN，图中断线，绝不自动补值。
    """
    table = sample.data.copy()
    f = ghz_to_hz(table.frequency_ghz)
    eps = make_complex(table.eps_real, table.eps_imag)
    mu = make_complex(table.mu_real, table.mu_imag)
    table["tan_delta_eps"] = loss_tangent(table.eps_real, table.eps_imag)
    table["tan_delta_mu"] = loss_tangent(table.mu_real, table.mu_imag)
    table["alpha_per_m"] = attenuation_constant(f, eps, mu)
    table["c0_seconds"] = eddy_current_c0(f, table.mu_real, table.mu_imag)
    for order in orders:
        table[f"quarter_wave_n{order}_mm"] = quarter_wave_thickness(f, eps, mu, order) * 1000
    warnings = []
    for col in table.columns[5:]:
        invalid = ~np.isfinite(table[col])
        if invalid.any():
            points = table.loc[invalid, "frequency_ghz"].tolist()
            warnings.append(f"[KNOWN] {col} 在 {points} GHz 未定义或数值溢出；派生结果保存为空值，绘图断线，不补值。")
            table.loc[invalid, col] = np.nan
    if (table.eps_imag < 0).any() or (table.mu_imag < 0).any():
        warnings.append("[COMMON] 存在负损耗系数；非负 α 公式不能据此证明被动性，需核查符号和反演。")
    return table, warnings


def quarter_wave_minima_comparison(result, parameter_table, orders=(1,)):
    """输入扫描结果和派生表；返回每个厚度所有并列 RLmin 处的理论厚度对照行。

    使用已有频率索引，不另行拟合峰位；差值仅作模型对照，不评价机理。
    """
    rows = []
    for i, thickness in enumerate(result.thickness_mm):
        for j in np.flatnonzero(result.rl_db[i] == np.min(result.rl_db[i])):
            row = {"frequency_ghz": float(result.frequency_ghz[j]), "actual_thickness_mm": float(thickness),
                   "rl_min_db": float(result.rl_db[i, j])}
            for order in orders:
                theoretical = float(parameter_table[f"quarter_wave_n{order}_mm"].iloc[j])
                row[f"quarter_wave_n{order}_mm"] = theoretical
                row[f"actual_minus_n{order}_mm"] = float(thickness) - theoretical
            rows.append(row)
    return rows
