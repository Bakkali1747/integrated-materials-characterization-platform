"""不可覆盖的科学分析运行记录。"""

from dataclasses import asdict, dataclass, field
from typing import Any

from core.common.validation_status import ValidationStatus


@dataclass(slots=True)
class AnalysisRun:
    analysis_run_id: str
    measurement_id: str
    analysis_type: str
    analysis_engine_version: str
    parameters: dict[str, Any] = field(default_factory=dict)
    software_version: str = ""
    git_commit: str = "unavailable"
    source_sha256: dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    validation_status: str = ValidationStatus.PENDING.value
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    result_refs: list[str] = field(default_factory=list)
    plot_refs: list[str] = field(default_factory=list)
    export_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AnalysisRun":
        return cls(**{name: value.get(name, field.default_factory() if callable(field.default_factory) else field.default)
                      for name, field in cls.__dataclass_fields__.items()})
