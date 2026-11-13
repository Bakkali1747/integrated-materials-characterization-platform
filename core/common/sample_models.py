"""以真实科研样品为中心的平台实体。"""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Sample:
    sample_id: str
    sample_name: str
    project_id: str
    material_system: str = ""
    batch: str = ""
    preparation_date: str = ""
    composition: dict[str, Any] | str = field(default_factory=dict)
    processing_conditions: dict[str, Any] | str = field(default_factory=dict)
    filler_ratio: str = ""
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Sample":
        return cls(**{name: value.get(name, field.default_factory() if callable(field.default_factory) else field.default)
                      for name, field in cls.__dataclass_fields__.items()})
