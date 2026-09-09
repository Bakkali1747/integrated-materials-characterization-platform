"""少量数据对象，集中声明单位和矩阵方向。"""

from dataclasses import dataclass, field
import numpy as np
import pandas as pd

COLUMNS = ["frequency_ghz", "eps_real", "eps_imag", "mu_real", "mu_imag"]


@dataclass
class SampleData:
    """表中虚部是损耗系数，复数构造时使用 real - j * imag。"""

    name: str
    data: pd.DataFrame
    metadata: dict
    warnings: list[str] = field(default_factory=list)


@dataclass
class RLResult:
    """rl_db 和 normalized_impedance 均为 (厚度点数, 频率点数)。"""

    frequency_ghz: np.ndarray
    thickness_mm: np.ndarray
    rl_db: np.ndarray
    normalized_impedance: np.ndarray
