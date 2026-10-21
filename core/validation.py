"""严格检查数据；不静默排序、删除、插值或修正符号。"""

import numpy as np

from core.models import COLUMNS


def summarize_values(values, limit=20):
    """输入数值序列；返回最多 limit 个值的紧凑文本，并注明总数。

    用于警告/错误文案，避免把上万个坏点拼进一条字符串；
    完整清单由分析服务另存为 data_quality.json / validation_errors.json。
    """
    values = [float(value) for value in values]
    shown = ", ".join(f"{value:g}" for value in values[:limit])
    if len(values) > limit:
        shown += f" …（共 {len(values)} 点）"
    return shown


def validate_data(data, sample_name, source_rows=None):
    """输入标准化表、样品名和源行号；错误抛异常，疑点返回中文警告。

    非有限值/无效频率阻止计算；负损耗值保留为质量警告，不判断机理。
    返回 (warnings, details)；details 保存可写入 JSON 的完整质量问题清单。
    """
    missing = [name for name in COLUMNS if name not in data.columns]
    if missing:
        raise ValueError(f"样品 {sample_name} 缺少列：{missing}")
    if len(data) < 2:
        raise ValueError(f"样品 {sample_name} 至少需要 2 个频率点。")
    values = data[COLUMNS].to_numpy(dtype=float)
    details = {"sample": sample_name, "negative_fields": {}, "near_zero_fields": [], "non_finite": []}
    errors = []
    for row, col in np.argwhere(~np.isfinite(values)):
        source = source_rows[row] if source_rows is not None else row + 1
        frequency = values[row, 0]
        errors.append(f"样品 {sample_name} 源行 {source}，{frequency:g} GHz 的 {COLUMNS[col]} 缺失或非有限。")
        details["non_finite"].append({"source_row": int(source), "frequency_ghz": None if not np.isfinite(frequency) else float(frequency),
                                      "column": COLUMNS[col]})
    if errors:
        message = (f"样品 {sample_name} 有 {len(errors)} 个缺失或非有限值；前 {min(20, len(errors))} 个：\n"
                   + "\n".join(errors[:20]))
        error = ValueError(message)
        error.details = details
        raise error
    frequency = values[:, 0]
    if np.any(frequency <= 0):
        raise ValueError(f"样品 {sample_name} 频率必须 > 0 GHz。")
    duplicates = np.unique(frequency, return_counts=True)
    repeated = duplicates[0][duplicates[1] > 1]
    if len(repeated):
        raise ValueError(f"样品 {sample_name} 存在重复频率 GHz：{repeated.tolist()}")
    if np.any(np.diff(frequency) <= 0):
        raise ValueError(f"样品 {sample_name} frequency 必须严格递增；未自动排序。")
    warnings = []
    for field in COLUMNS[1:]:
        mask = data[field].to_numpy() < 0
        if np.any(mask):
            frequencies = frequency[mask].tolist()
            details["negative_fields"][field] = {"count": len(frequencies), "frequency_ghz": frequencies}
            warnings.append(f"[KNOWN] {field} 有 {len(frequencies)} 个负值，频率 GHz："
                            f"{summarize_values(frequencies)}；已保留原值，完整清单见 data_quality.json。")
    for field in ("eps_real", "mu_real"):
        if np.any(np.abs(data[field]) < 1e-10):
            details["near_zero_fields"].append(field)
            warnings.append(f"[KNOWN] {field} 存在接近零的数值，需要检查测量及反演设置。")
    return warnings, details
