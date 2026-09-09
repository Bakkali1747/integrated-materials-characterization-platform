"""复阻抗分析；模长接近 1 不等于完整复数匹配。"""

import numpy as np


def impedance_at_minima(result):
    """输入 RL 结果；返回所有网格全局最小值处 z 的实部、虚部、模长与 |z−1|。

    全部无量纲；[COMMON] 完整匹配要求 z 接近 1+j0，不能只看 |z|。
    """
    rows = []
    for i, j in np.argwhere(result.rl_db == np.min(result.rl_db)):
        z = result.normalized_impedance[i, j]
        rows.append({"frequency_ghz": float(result.frequency_ghz[j]),
                     "thickness_mm": float(result.thickness_mm[i]), "rl_db": float(result.rl_db[i, j]),
                     "z_real": float(z.real), "z_imag": float(z.imag),
                     "z_abs": float(abs(z)), "distance_to_1_plus_0j": float(abs(z-1))})
    return rows
