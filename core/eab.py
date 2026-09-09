"""[COMMON] 固定厚度最大连续带宽；不同频段宽度不相加称为 EAB。"""

import numpy as np


def merge_intervals(intervals):
    """输入起止频率对(GHz)；返回相交或相接区间的并集，保留分离频段。"""
    merged = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([float(start), float(end)])
        else:
            merged[-1][1] = max(merged[-1][1], float(end))
    return merged


def absorption_bands(frequency_ghz, rl_db, threshold=-10.0, crossing="linear"):
    """输入固定厚度的一维频率/RL；返回带宽、全部连续频段及并列最大频段。

    输出宽度单位 GHz。linear 只估计相邻有效采样点间的阈值交点，不补缺失数据；
    sample 使用合格采样点的首尾。相等阈值也合格，孤立触点宽度为零。
    测量端点处合格的频段标为 touches_*_boundary，不推断测量范围外响应。
    """
    f, y = np.asarray(frequency_ghz, dtype=float), np.asarray(rl_db, dtype=float)
    if f.ndim != 1 or y.shape != f.shape or len(f) < 2:
        raise ValueError("EAB 需要至少两个等长一维频率/RL 点。")
    if not np.isfinite(f).all() or np.any(f <= 0) or np.any(np.diff(f) <= 0):
        raise ValueError("EAB 频率必须有限、正值且严格递增。")
    if np.isnan(y).any() or np.isposinf(y).any() or not np.isfinite(threshold):
        raise ValueError("EAB 不接受缺失 RL、正无穷 RL 或非有限阈值；不会跨缺失点插值。")
    if crossing not in ("linear", "sample"):
        raise ValueError("阈值边界方法必须为 linear 或 sample。")
    inside = y <= threshold
    intervals = []
    if crossing == "sample":
        start = None
        for index, hit in enumerate(inside):
            if hit and start is None:
                start = index
            if start is not None and (not hit or index == len(f) - 1):
                end = index if hit else index - 1
                intervals.append([f[start], f[end]])
                start = None
    else:
        for index in range(len(f) - 1):
            left, right = inside[index], inside[index + 1]
            if left and right:
                intervals.append([f[index], f[index + 1]])
            elif left != right:
                if not np.isfinite(y[index:index + 2]).all():
                    raise ValueError("阈值跨越涉及 -inf，无法线性估计交点；可显式选择 sample 模式。")
                fraction = (threshold - y[index]) / (y[index + 1] - y[index])
                edge = f[index] + fraction * (f[index + 1] - f[index])
                intervals.append([f[index], edge] if left else [edge, f[index + 1]])
    bands = []
    for start, end in merge_intervals(intervals):
        bands.append({"start_ghz": start, "end_ghz": end, "width_ghz": end - start,
                      "touches_lower_boundary": bool(start == f[0]), "touches_upper_boundary": bool(end == f[-1])})
    maximum = max((band["width_ghz"] for band in bands), default=0.)
    # 1e-12 GHz 仅用于浮点并列判断，不修改阈值条件或频段边界。
    widest = [band for band in bands if np.isclose(band["width_ghz"], maximum, rtol=0, atol=1e-12)]
    return {"threshold_db": float(threshold), "crossing": crossing, "maximum_continuous_bandwidth_ghz": maximum,
            "bands": bands, "widest_bands": widest}


def summarize_bandwidths(result, threshold=-10.0, crossing="linear"):
    """输入 RL 扫描结果；返回逐厚度频带、最大带宽及全部并列最佳厚度。

    阈值 -10 dB 时指标名为 EAB；其他阈值只能称指定阈值最大连续带宽。
    无正宽度频段时最佳厚度列表为空，避免把全部厚度称为最佳吸收厚度。
    """
    by_thickness = []
    for thickness, curve in zip(result.thickness_mm, result.rl_db):
        entry = absorption_bands(result.frequency_ghz, curve, threshold, crossing)
        entry["thickness_mm"] = float(thickness)
        by_thickness.append(entry)
    maximum = max(entry["maximum_continuous_bandwidth_ghz"] for entry in by_thickness)
    best = [entry for entry in by_thickness
            if maximum > 0 and np.isclose(entry["maximum_continuous_bandwidth_ghz"], maximum, rtol=0, atol=1e-12)]
    return {"metric": "EAB" if threshold == -10 else f"Maximum continuous bandwidth at {threshold:g} dB",
            "threshold_db": float(threshold), "crossing": crossing, "maximum_bandwidth_ghz": maximum,
            "best_thicknesses": best, "by_thickness": by_thickness}


def cumulative_frequency_coverage(by_thickness):
    """输入逐厚度频段结果；返回已扫描厚度的频段并集与总覆盖宽度(GHz)。

    [COMMON] 此总覆盖不是 EAB，也不代表同一厚度可实现该覆盖。
    """
    intervals = [[band["start_ghz"], band["end_ghz"]] for entry in by_thickness for band in entry["bands"]]
    merged = merge_intervals(intervals)
    return {"metric": "Cumulative Frequency Coverage", "intervals_ghz": merged,
            "total_coverage_ghz": sum(end-start for start, end in merged), "scope": "scanned thicknesses only"}
