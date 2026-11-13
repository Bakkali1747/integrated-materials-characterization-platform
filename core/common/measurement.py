"""一次真实仪器测试及其只读源文件引用。"""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from core.common.validation_status import ValidationStatus


class MeasurementType(str, Enum):
    ELECTROMAGNETIC = "electromagnetic"
    VSM = "vsm"
    XRD = "xrd"

    @property
    def label(self) -> str:
        return {self.ELECTROMAGNETIC: "Electromagnetic", self.VSM: "VSM", self.XRD: "XRD"}[self]

    @classmethod
    def coerce(cls, value: "MeasurementType | str") -> "MeasurementType":
        if isinstance(value, cls):
            return value
        return cls(str(value).strip().lower())


@dataclass(slots=True)
class Measurement:
    measurement_id: str
    sample_id: str
    measurement_type: str
    source_files: list[str] = field(default_factory=list)
    source_sha256: dict[str, str] = field(default_factory=dict)
    instrument: str = ""
    measurement_date: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    validation_status: str = ValidationStatus.PENDING.value
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Measurement":
        return cls(**{name: value.get(name, field.default_factory() if callable(field.default_factory) else field.default)
                      for name, field in cls.__dataclass_fields__.items()})
