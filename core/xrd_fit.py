"""XRD 单峰 Pseudo-Voigt 拟合；局部线性基线，不依赖 scipy。"""

import math

import numpy as np

FIT_METHOD = "pseudo_voigt_local_linear_baseline"


def pseudo_voigt(x, center, fwhm, eta, amplitude, baseline0, baseline1):
    """Pseudo-Voigt 峰 + 局部线性基线；fwhm 为半高全宽（度）。"""
    if fwhm <= 0:
        return np.full_like(np.asarray(x, dtype=float), np.nan)
    z = (np.asarray(x, dtype=float) - center) / fwhm
    gaussian = np.exp(-4.0 * math.log(2.0) * z * z)
    lorentzian = 1.0 / (1.0 + 4.0 * z * z)
    return baseline0 + baseline1 * (np.asarray(x, dtype=float) - center) + \
        amplitude * ((1.0 - eta) * gaussian + eta * lorentzian)


def _linear_solve(x, y, center, fwhm, eta):
    z = (x - center) / fwhm
    gaussian = np.exp(-4.0 * math.log(2.0) * z * z)
    lorentzian = 1.0 / (1.0 + 4.0 * z * z)
    shape = (1.0 - eta) * gaussian + eta * lorentzian
    design = np.column_stack([shape, np.ones_like(x), x - center])
    try:
        coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    except np.linalg.LinAlgError:
        return math.inf, None
    amplitude, baseline0, baseline1 = coefficients
    if not np.isfinite(coefficients).all() or amplitude <= 0:
        return math.inf, None
    residual = y - design @ coefficients
    return float(np.sum(residual ** 2)), (float(amplitude), float(baseline0), float(baseline1))


def _golden_minimize(function, low, high, iterations=35):
    invphi = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = float(low), float(high)
    c = b - invphi * (b - a)
    d = a + invphi * (b - a)
    fc, fd = function(c), function(d)
    for _ in range(iterations):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - invphi * (b - a)
            fc = function(c)
        else:
            a, c, fc = c, d, fd
            d = a + invphi * (b - a)
            fd = function(d)
    return (a + b) / 2.0


def fit_pseudo_voigt(x, y, center_guess, fwhm_guess=None, step=None):
    """在峰附近窗口拟合 Pseudo-Voigt；返回拟合参数或 converged=False。"""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 8 or len(x) != len(y):
        return {"converged": False, "reason": "窗口点数不足或数据不等长"}
    if step is None:
        step = float(np.median(np.diff(x)))
    if not np.isfinite(step) or step <= 0:
        return {"converged": False, "reason": "扫描步长无效"}
    fwhm0 = float(fwhm_guess) if fwhm_guess is not None and np.isfinite(fwhm_guess) and fwhm_guess > 0 \
        else max(20.0 * step, .2)
    half = max(2.5 * fwhm0, 15.0 * step, .15)
    mask = np.abs(x - center_guess) <= half
    if mask.sum() < 8:
        return {"converged": False, "reason": "峰窗口内点数不足 8"}
    local_x, local_y = x[mask], y[mask]
    span = float(local_x.max() - local_x.min())
    if span <= 0 or np.ptp(local_y) <= 0:
        return {"converged": False, "reason": "窗口内强度或 2θ 无变化"}
    fwhm_low = max(1.5 * step, 1e-4)
    fwhm_high = max(span * .8, fwhm_low * 2)
    center_low = max(float(local_x.min()) + fwhm_low, center_guess - max(fwhm0, half / 2))
    center_high = min(float(local_x.max()) - fwhm_low, center_guess + max(fwhm0, half / 2))
    if center_low >= center_high:
        return {"converged": False, "reason": "峰中心边界无效"}
    center, fwhm, eta = float(center_guess), float(np.clip(fwhm0, fwhm_low, fwhm_high)), .5

    def objective(c, f, e):
        sse, _ = _linear_solve(local_x, local_y, c, f, e)
        return sse

    previous = objective(center, fwhm, eta)
    if not np.isfinite(previous):
        return {"converged": False, "reason": "初始线性解无效"}
    for _ in range(6):
        center = _golden_minimize(lambda value: objective(value, fwhm, eta), center_low, center_high)
        log_fwhm = _golden_minimize(lambda value: objective(center, math.exp(value), eta),
                                    math.log(fwhm_low), math.log(fwhm_high))
        fwhm = math.exp(log_fwhm)
        eta = _golden_minimize(lambda value: objective(center, fwhm, value), 0.0, 1.0)
        current = objective(center, fwhm, eta)
        if not np.isfinite(current):
            return {"converged": False, "reason": "拟合目标函数出现非有限值"}
        if abs(previous - current) <= 1e-10 * max(1.0, previous):
            previous = current
            break
        previous = current
    sse, coefficients = _linear_solve(local_x, local_y, center, fwhm, eta)
    if coefficients is None:
        return {"converged": False, "reason": "最终线性解无效"}
    amplitude, baseline0, baseline1 = coefficients
    total = float(np.sum((local_y - np.mean(local_y)) ** 2))
    r_squared = float(1.0 - sse / total) if total > 0 else None
    fitted = pseudo_voigt(local_x, center, fwhm, eta, amplitude, baseline0, baseline1)
    return {
        "converged": True, "method": FIT_METHOD,
        "center_deg": float(center), "fwhm_deg": float(fwhm), "eta": float(eta),
        "amplitude": float(amplitude), "baseline0": float(baseline0),
        "baseline1": float(baseline1), "r_squared": r_squared,
        "point_count": int(len(local_x)), "window_deg": [float(local_x.min()), float(local_x.max())],
        "sse": float(sse), "fitted": fitted, "x": local_x,
    }
