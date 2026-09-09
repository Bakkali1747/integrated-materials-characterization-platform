"""单位在这里统一转换，函数名显式写出单位。"""

from decimal import Decimal, ROUND_FLOOR
import numpy as np

C = 299_792_458.0  # [KNOWN] 真空光速，m/s。
Z0 = 376.730313668  # [KNOWN] 自由空间阻抗近似值，ohm。


def ghz_to_hz(frequency_ghz):
    """输入 GHz 数值或数组；返回同形状 Hz 数值，供 SI 制公式使用。"""
    return np.asarray(frequency_ghz, dtype=float) * 1e9


def mm_to_m(thickness_mm):
    """输入 mm 数值或数组；返回同形状 m 数值，供传播相位计算使用。"""
    return np.asarray(thickness_mm, dtype=float) * 1e-3


def thickness_grid(start_mm=1.0, stop_mm=5.0, step_mm=0.01):
    """输入厚度上下限与步长(mm)；返回递增一维网格，不超过上限。

    十进制计数避免 0.01 的浮点误差遗漏终点；不整除时不增加非等距末点。
    """
    values = np.asarray([start_mm, stop_mm, step_mm], dtype=float)
    if not np.isfinite(values).all() or start_mm <= 0 or stop_mm < start_mm or step_mm <= 0:
        raise ValueError("厚度必须有限：0 < 起点 <= 终点，步长 > 0；单位 mm。")
    start, stop, step = [Decimal(str(v)) for v in values]
    count = int(((stop - start) / step).to_integral_value(rounding=ROUND_FLOOR)) + 1
    if count > 100_000:
        raise ValueError("厚度点数超过 100000，请增大步长。")
    return np.array([float(start + i * step) for i in range(count)])
