"""本地优先工作区；保存实体引用，不改写或搬动原始科研文件。"""

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from core import __version__
from core.common.analysis_run import AnalysisRun
from core.common.measurement import Measurement, MeasurementType
from core.common.project_models import Project
from core.common.sample_models import Sample
from core.common.validation_status import ValidationStatus

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _checked_id(value: str, field: str) -> str:
    value = str(value).strip()
    if not _SAFE_ID.fullmatch(value):
        raise ValueError(f"{field} 只能包含字母、数字、点、下划线和连字符，且不超过 128 个字符。")
    return value


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class WorkspaceRepository:
    """以 project/sample 目录组织 JSON 记录；所有写入均使用临时文件原子替换。"""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.projects_root = self.root / "projects"
        self.projects_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _project_dir(self, project_id: str) -> Path:
        return self.projects_root / _checked_id(project_id, "project_id")

    def _sample_dir(self, project_id: str, sample_id: str) -> Path:
        return self._project_dir(project_id) / "samples" / _checked_id(sample_id, "sample_id")

    def create_project(self, project_name: str, *, description: str = "", tags: Iterable[str] = (),
                       notes: str = "", project_id: str | None = None) -> Project:
        name = str(project_name).strip()
        if not name:
            raise ValueError("项目名称不能为空。")
        identifier = _checked_id(project_id or _new_id("prj"), "project_id")
        folder = self._project_dir(identifier)
        if (folder / "project.json").exists():
            raise ValueError(f"项目 ID 已存在：{identifier}")
        now = _now()
        project = Project(identifier, name, str(description).strip(), now, now,
                          [str(item).strip() for item in tags if str(item).strip()], str(notes).strip(), [], str(folder))
        self._write_json(folder / "project.json", project.to_dict())
        return project

    def list_projects(self) -> list[Project]:
        projects = [Project.from_dict(self._read_json(path)) for path in self.projects_root.glob("*/project.json")]
        return sorted(projects, key=lambda item: (item.updated_at, item.project_name), reverse=True)

    def get_project(self, project_id: str) -> Project:
        path = self._project_dir(project_id) / "project.json"
        if not path.is_file():
            raise KeyError(f"项目不存在：{project_id}")
        return Project.from_dict(self._read_json(path))

    def _save_project(self, project: Project) -> None:
        project.updated_at = _now()
        self._write_json(self._project_dir(project.project_id) / "project.json", project.to_dict())

    def create_sample(self, project_id: str, sample_name: str, *, sample_id: str | None = None,
                      material_system: str = "", batch: str = "", preparation_date: str = "",
                      composition: dict[str, Any] | str | None = None,
                      processing_conditions: dict[str, Any] | str | None = None,
                      filler_ratio: str = "", notes: str = "", tags: Iterable[str] = ()) -> Sample:
        project = self.get_project(project_id)
        name = str(sample_name).strip()
        if not name:
            raise ValueError("样品名称不能为空。")
        identifier = _checked_id(sample_id or _new_id("smp"), "sample_id")
        if self.find_sample(identifier) is not None:
            raise ValueError(f"样品 ID 已存在：{identifier}")
        now = _now()
        sample = Sample(identifier, name, project.project_id, str(material_system).strip(), str(batch).strip(),
                        str(preparation_date).strip(), composition if composition is not None else {},
                        processing_conditions if processing_conditions is not None else {}, str(filler_ratio).strip(),
                        str(notes).strip(), [str(item).strip() for item in tags if str(item).strip()], now, now)
        self._write_json(self._sample_dir(project.project_id, identifier) / "sample.json", sample.to_dict())
        project.sample_ids.append(identifier)
        self._save_project(project)
        return sample

    def list_samples(self, project_id: str | None = None) -> list[Sample]:
        paths = (self._project_dir(project_id) / "samples").glob("*/sample.json") if project_id else self.projects_root.glob("*/samples/*/sample.json")
        samples = [Sample.from_dict(self._read_json(path)) for path in paths]
        return sorted(samples, key=lambda item: (item.updated_at, item.sample_id), reverse=True)

    def find_sample(self, sample_id: str) -> Sample | None:
        identifier = _checked_id(sample_id, "sample_id")
        matches = list(self.projects_root.glob(f"*/samples/{identifier}/sample.json"))
        return Sample.from_dict(self._read_json(matches[0])) if matches else None

    def get_sample(self, project_id: str, sample_id: str) -> Sample:
        path = self._sample_dir(project_id, sample_id) / "sample.json"
        if not path.is_file():
            raise KeyError(f"样品不存在：{sample_id}")
        return Sample.from_dict(self._read_json(path))

    def _touch_sample(self, project_id: str, sample_id: str) -> None:
        sample = self.get_sample(project_id, sample_id)
        sample.updated_at = _now()
        self._write_json(self._sample_dir(project_id, sample_id) / "sample.json", sample.to_dict())
        self._save_project(self.get_project(project_id))

    def add_measurement(self, project_id: str, sample_id: str, measurement_type: MeasurementType | str,
                        source_files: Iterable[str | Path], *, instrument: str = "", measurement_date: str = "",
                        raw_metadata: dict[str, Any] | None = None,
                        validation_status: ValidationStatus | str = ValidationStatus.PENDING,
                        measurement_id: str | None = None) -> Measurement:
        self.get_sample(project_id, sample_id)
        kind = MeasurementType.coerce(measurement_type)
        files = [Path(item).expanduser().resolve() for item in source_files]
        if not files:
            raise ValueError("至少选择一个原始测试文件。")
        missing = [str(path) for path in files if not path.is_file()]
        if missing:
            raise FileNotFoundError("原始文件不存在：" + "；".join(missing))
        identifier = _checked_id(measurement_id or _new_id("mea"), "measurement_id")
        path = self._sample_dir(project_id, sample_id) / "measurements" / f"{identifier}.json"
        if path.exists():
            raise ValueError(f"Measurement ID 已存在：{identifier}")
        hashes = {str(source): _hash_file(source) for source in files}
        measurement = Measurement(identifier, sample_id, kind.value, [str(source) for source in files], hashes,
                                  str(instrument).strip(), str(measurement_date).strip(), raw_metadata or {},
                                  ValidationStatus.coerce(validation_status).value, _now())
        self._write_json(path, measurement.to_dict())
        self._touch_sample(project_id, sample_id)
        return measurement

    def list_measurements(self, project_id: str, sample_id: str) -> list[Measurement]:
        folder = self._sample_dir(project_id, sample_id) / "measurements"
        values = [Measurement.from_dict(self._read_json(path)) for path in folder.glob("*.json")]
        return sorted(values, key=lambda item: item.created_at, reverse=True)

    def get_measurement(self, project_id: str, sample_id: str, measurement_id: str) -> Measurement:
        path = self._sample_dir(project_id, sample_id) / "measurements" / f"{_checked_id(measurement_id, 'measurement_id')}.json"
        if not path.is_file():
            raise KeyError(f"Measurement 不存在：{measurement_id}")
        return Measurement.from_dict(self._read_json(path))

    def set_measurement_validation(self, project_id: str, sample_id: str, measurement_id: str,
                                   validation_status: ValidationStatus | str) -> Measurement:
        """记录测试层面的最新科研状态；调用方负责不把未验证结果升级为 VALIDATED。"""
        path = self._sample_dir(project_id, sample_id) / "measurements" / f"{_checked_id(measurement_id, 'measurement_id')}.json"
        if not path.is_file():
            raise KeyError(f"Measurement 不存在：{measurement_id}")
        measurement = Measurement.from_dict(self._read_json(path))
        measurement.validation_status = ValidationStatus.coerce(validation_status).value
        self._write_json(path, measurement.to_dict())
        self._touch_sample(project_id, sample_id)
        return measurement

    def verify_measurement_sources(self, project_id: str, sample_id: str, measurement_id: str) -> dict[str, str]:
        measurement = self.get_measurement(project_id, sample_id, measurement_id)
        states: dict[str, str] = {}
        for name, expected in measurement.source_sha256.items():
            path = Path(name)
            states[name] = "MISSING" if not path.is_file() else "PASS" if _hash_file(path) == expected else "CHANGED"
        return states

    def add_analysis_run(self, project_id: str, sample_id: str, measurement_id: str, *, analysis_type: str,
                         analysis_engine_version: str, parameters: dict[str, Any] | None = None,
                         git_commit: str = "unavailable",
                         validation_status: ValidationStatus | str = ValidationStatus.PENDING,
                         warnings: Iterable[str] = (), errors: Iterable[str] = (), result_refs: Iterable[str] = (),
                         plot_refs: Iterable[str] = (), export_refs: Iterable[str] = (),
                         analysis_run_id: str | None = None) -> AnalysisRun:
        measurement = self.get_measurement(project_id, sample_id, measurement_id)
        identifier = _checked_id(analysis_run_id or _new_id("run"), "analysis_run_id")
        path = self._sample_dir(project_id, sample_id) / "analyses" / f"{identifier}.json"
        if path.exists():
            raise ValueError(f"AnalysisRun ID 已存在：{identifier}")
        run = AnalysisRun(identifier, measurement.measurement_id, str(analysis_type).strip(),
                          str(analysis_engine_version).strip(), parameters or {}, __version__, str(git_commit),
                          dict(measurement.source_sha256), _now(), ValidationStatus.coerce(validation_status).value,
                          list(warnings), list(errors), list(result_refs), list(plot_refs), list(export_refs))
        if not run.analysis_type or not run.analysis_engine_version:
            raise ValueError("analysis_type 和 analysis_engine_version 不能为空。")
        self._write_json(path, run.to_dict())
        self._touch_sample(project_id, sample_id)
        return run

    def list_analysis_runs(self, project_id: str, sample_id: str, measurement_id: str | None = None) -> list[AnalysisRun]:
        folder = self._sample_dir(project_id, sample_id) / "analyses"
        values = [AnalysisRun.from_dict(self._read_json(path)) for path in folder.glob("*.json")]
        if measurement_id:
            values = [item for item in values if item.measurement_id == measurement_id]
        return sorted(values, key=lambda item: item.created_at, reverse=True)

    def add_analysis_run_export_refs(self, project_id: str, sample_id: str, analysis_run_id: str,
                                     paths: Iterable[str | Path]) -> AnalysisRun:
        """把显式导出文件追加到运行记录；去重且不删除已有引用。"""
        path = self._sample_dir(project_id, sample_id) / "analyses" / f"{_checked_id(analysis_run_id, 'analysis_run_id')}.json"
        if not path.is_file():
            raise KeyError(f"AnalysisRun 不存在：{analysis_run_id}")
        run = AnalysisRun.from_dict(self._read_json(path))
        known = set(run.export_refs)
        for item in paths:
            value = str(Path(item).expanduser().resolve())
            if value not in known:
                run.export_refs.append(value)
                known.add(value)
        self._write_json(path, run.to_dict())
        self._touch_sample(project_id, sample_id)
        return run

    def find_analysis_run_by_result_directory(self, directory: str | Path) -> tuple[str, str, AnalysisRun] | None:
        """按结果目录反查运行，用于把显式导出追加到对应记录。"""
        needle = str(Path(directory).expanduser().resolve())
        for path in self.projects_root.glob("*/samples/*/analyses/*.json"):
            run = AnalysisRun.from_dict(self._read_json(path))
            if run.result_refs and str(Path(run.result_refs[0]).expanduser().resolve()) == needle:
                relative = path.relative_to(self.projects_root)
                return relative.parts[0], relative.parts[2], run
        return None
