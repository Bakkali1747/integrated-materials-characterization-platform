"""[COMMON] 法向入射、均匀单层、理想金属背板的传输线模型。"""

import numpy as np
from core.units import C, ghz_to_hz, mm_to_m
from core.models import RLResult


def normalized_input_impedance(frequency_hz, eps_complex, mu_complex, thickness_m):
    """输入一维 f(Hz)、相对 ε/μ 复数及一维 d(m)，返回 z=Zin/Z0。

    shape=(Nd,Nf)。2πfd/c 必须无量纲，因此 f 与 d 必须为 SI 单位。
    使用同一个折射率分支构造 zc=μ/n，保证 zc*n=μ；翻转 n 的符号不改变
    有限层结果。小传播相位使用 tanh(x)/x 的级数，避免 n=0 时出现 0/0。
    """
    f = np.asarray(frequency_hz, dtype=float)
    eps, mu = np.asarray(eps_complex, dtype=complex), np.asarray(mu_complex, dtype=complex)
    d = np.atleast_1d(np.asarray(thickness_m, dtype=float))
    if f.ndim != 1 or eps.shape != f.shape or mu.shape != f.shape or d.ndim != 1 or not len(f) or not len(d):
        raise ValueError("f、ε、μ 必须是等长一维数组；d 必须是一维非空数组。")
    if not all(np.isfinite(a).all() for a in (f, eps, mu, d)) or np.any(f <= 0) or np.any(d < 0):
        raise ValueError("计算输入必须有限，f > 0 Hz，d >= 0 m。")
    if len(f) * len(d) > 5_000_000:
        raise ValueError("RL 网格超过 500 万点，请缩小范围或增大步长。")
    k0d = 2 * np.pi * d[:, None] * f[None, :] / C
    n = np.sqrt(eps * mu)
    x = 1j * k0d * n[None, :]
    ratio = np.empty_like(x)
    small = np.abs(x) < 1e-5
    ratio[small] = 1 - x[small] ** 2 / 3 + 2 * x[small] ** 4 / 15
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            ratio[~small] = np.tanh(x[~small]) / x[~small]
            z = 1j * k0d * mu[None, :] * ratio
        except FloatingPointError as error:
            raise ValueError("输入阻抗计算遇到数值奇异，请检查参数。") from error
    if not np.isfinite(z).all():
        raise ValueError("输入阻抗包含非有限值。")
    return z


def calculate_rl(frequency_hz, eps_complex, mu_complex, thickness_m):
    """输入 SI 制频率/厚度与相对复参数；返回 RL(dB)，shape=(Nd,Nf)。

    [COMMON] RL=20log10|(z-1)/(z+1)|；精确零反射保留 -inf，不人为截断。
    """
    z = normalized_input_impedance(frequency_hz, eps_complex, mu_complex, thickness_m)
    return rl_from_impedance(z)


def rl_from_impedance(z):
    """输入无量纲归一化复阻抗；返回同形状 RL(dB)，拒绝反射公式奇点。"""
    z = np.asarray(z, dtype=complex)
    if not np.isfinite(z).all() or np.any(z + 1 == 0):
        raise ValueError("反射公式输入非有限或 z+1=0。")
    with np.errstate(divide="ignore"):
        return 20 * np.log10(np.abs((z - 1) / (z + 1)))


def scan_rl(frequency_ghz, eps_complex, mu_complex, thickness_mm):
    """输入展示单位 GHz/mm；返回带坐标的结果对象，不改变 RL 原始数值。"""
    f, d = np.asarray(frequency_ghz, dtype=float), np.asarray(thickness_mm, dtype=float)
    z = normalized_input_impedance(ghz_to_hz(f), eps_complex, mu_complex, mm_to_m(d))
    return RLResult(f, d, rl_from_impedance(z), z)


def minimum_points(result):
    """输入扫描结果；返回网格内所有精确并列的最小值位置，不插值搜索。"""
    minimum = np.min(result.rl_db)
    return [{"rl_min_db": float(minimum), "frequency_ghz": float(result.frequency_ghz[j]),
             "thickness_mm": float(result.thickness_mm[i])}
            for i, j in np.argwhere(result.rl_db == minimum)]
