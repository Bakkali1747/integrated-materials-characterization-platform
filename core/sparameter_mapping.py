"""S 参数列映射与已知数据网格配置，独立于物理计算。索引从 0 开始。"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import numpy as np

S_NAMES = ("S11", "S21", "S12", "S22")


@dataclass
class SParameterMapping:
    """用户提供的高置信候选 schema；不等同厂商确认，列顺序可配置。"""

    schema_id: str = "cip_sio2_sdat_candidate_v1"
    schema_status: str = "candidate_high_confidence"
    frequency_column: int = 0
    frequency_unit: str = "GHz"
    complex_columns: dict = field(default_factory=lambda: {
        "S11": [1, 2], "S21": [3, 4], "S12": [5, 6], "S22": [7, 8]})
    expected_points: int | None = 201
    expected_frequency_start_ghz: float | None = 2.0
    expected_frequency_stop_ghz: float | None = 18.0
    expected_frequency_step_ghz: float | None = 0.08
    frequency_grid_atol_ghz: float = 1e-9

    def validate(self):
        """校验配置字段和列索引；不允许重用/遗漏九列或偷偷提升为厂商确认。"""
        if not isinstance(self.schema_id, str) or not self.schema_id.strip():
            raise ValueError("schema_id 必须为非空字符串。")
        if self.schema_status not in ("candidate_high_confidence", "unverified"):
            raise ValueError("当前只支持 candidate_high_confidence 或 unverified，不支持厂商确认状态。")
        if self.frequency_unit not in ("Hz", "kHz", "MHz", "GHz"):
            raise ValueError("S 参数频率单位必须显式为 Hz/kHz/MHz/GHz。")
        if set(self.complex_columns) != set(S_NAMES):
            raise ValueError("必须配置 S11/S21/S12/S22 四组列。")
        indices = [self.frequency_column]
        for name in S_NAMES:
            pair = self.complex_columns[name]
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError(f"{name} 必须指定 [real_column, imag_column]。")
            indices.extend(pair)
        if any(type(index) is not int for index in indices) or sorted(indices) != list(range(9)):
            raise ValueError("列索引必须无重复地覆盖 0–8 九列。")
        if self.expected_points is not None and (type(self.expected_points) is not int or self.expected_points < 1):
            raise ValueError("expected_points 必须为正整数或 null。")
        for key in ("expected_frequency_start_ghz", "expected_frequency_stop_ghz", "expected_frequency_step_ghz", "frequency_grid_atol_ghz"):
            value = getattr(self, key)
            if value is not None and (isinstance(value, bool) or not np.isfinite(value) or value <= 0):
                raise ValueError(f"{key} 必须为有限正数，非必要约束可以设为 null。")
        if self.frequency_grid_atol_ghz is None:
            raise ValueError("频率网格容差不能为 null。")
        if self.expected_frequency_start_ghz is not None and self.expected_frequency_stop_ghz is not None:
            if self.expected_frequency_start_ghz > self.expected_frequency_stop_ghz:
                raise ValueError("预期频率起点不能大于终点。")

    def to_dict(self):
        """返回完整可序列化配置，记录实际应用的所有默认值与映射。"""
        return asdict(self)


def load_sparameter_mapping(path):
    """输入 JSON 配置路径；返回校验后的映射，未知配置字段明确报错。"""
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("S 参数 schema 必须是 JSON 对象。")
    if "schema_status" not in payload or "complex_columns" not in payload:
        raise ValueError("自定义 schema 必须显式包含 schema_status 和 complex_columns。")
    try:
        mapping = SParameterMapping(**payload)
    except TypeError as error:
        raise ValueError(f"未知或无效 schema 字段：{error}") from error
    mapping.validate()
    return mapping
