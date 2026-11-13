"""科研项目实体。"""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Project:
    project_id: str
    project_name: str
    description: str = ""
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    sample_ids: list[str] = field(default_factory=list)
    project_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Project":
        return cls(**{name: value.get(name, field.default_factory() if callable(field.default_factory) else field.default)
                      for name, field in cls.__dataclass_fields__.items()})
