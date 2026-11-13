"""全平台统一的科研验证状态。"""

from enum import Enum


class ValidationStatus(str, Enum):
    VALIDATED = "VALIDATED"
    PENDING = "PENDING"
    WARNING = "WARNING"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @classmethod
    def coerce(cls, value: "ValidationStatus | str") -> "ValidationStatus":
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().upper().replace(" ", "_")
        return cls(normalized)
