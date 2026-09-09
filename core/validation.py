"""严格检查数据；不静默排序、删除、插值或修正符号。"""

import numpy as np
from core.models import COLUMNS


def validate_data(data, sample_name, source_rows=None):
    """输入标准化表、样品名和源行号；错误抛异常，疑点返回中文警告。

    非有限值/无效频率阻止计算；负损耗值保留为质量警告，不判断机理。
    """
    missing = [name for name in COLUMNS if name not in data.columns]
    if missing:
        raise ValueError(f"样品 {sample_name} 缺少列：{missing}")
    if len(data) < 2:
        raise ValueError(f"样品 {sample_name} 至少需要 2 个频率点。")
    values = data[COLUMNS].to_numpy(dtype=float)
    errors = []
    for row, col in np.argwhere(~np.isfinite(values)):
        source = source_rows[row] if source_rows is not None else row + 1
        freq = values[row, 0]
        errors.append(f"样品 {sample_name} 源行 {source}，{freq:g} GHz 的 {COLUMNS[col]} 缺失或非有限。")
    if errors:
        raise ValueError("\n".join(errors))
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
            points = ", ".join(f"{v:g}" for v in frequency[mask])
            warnings.append(f"[KNOWN] {field} 有 {int(mask.sum())} 个负值，频率 GHz：{points}；已保留原值。")
    for field in ("eps_real", "mu_real"):
        if np.any(np.abs(data[field]) < 1e-10):
            warnings.append(f"[KNOWN] {field} 存在接近零的数值，需要检查测量及反演设置。")
    return warnings
