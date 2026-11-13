"""Phase A 项目、样品、测试和分析运行工作区。"""

import hashlib

import pytest

from core.common import MeasurementType, ValidationStatus, WorkspaceRepository
from gui.pages.workspace_page import WorkspacePage


def test_validation_status_is_canonical():
    assert ValidationStatus.coerce("not computable") is ValidationStatus.NOT_COMPUTABLE
    assert ValidationStatus.NOT_COMPUTABLE.label == "NOT COMPUTABLE"
    with pytest.raises(ValueError):
        ValidationStatus.coerce("success")


def test_workspace_lifecycle_and_source_integrity(tmp_path):
    source = tmp_path / "FCIP-03.dat"
    original = b"instrument data\r\n1,2,3\r\n"
    source.write_bytes(original)
    repository = WorkspaceRepository(tmp_path / "workspace")

    project = repository.create_project("片状 CIP 磁性能调控", tags=["CIP", "VSM"])
    sample = repository.create_sample(
        project.project_id,
        "片状 CIP",
        sample_id="FCIP-03",
        material_system="Carbonyl Iron Powder",
        filler_ratio="40 wt%",
        composition={"matrix": "Paraffin"},
        processing_conditions={"ball_milling": "2 h"},
    )
    measurement = repository.add_measurement(
        project.project_id,
        sample.sample_id,
        MeasurementType.VSM,
        [source],
        instrument="VSM",
        measurement_date="2026-11-13",
    )

    assert source.read_bytes() == original
    assert measurement.source_files == [str(source.resolve())]
    assert measurement.source_sha256[str(source.resolve())] == hashlib.sha256(original).hexdigest()
    assert repository.verify_measurement_sources(project.project_id, sample.sample_id, measurement.measurement_id) == {
        str(source.resolve()): "PASS"
    }
    loaded = repository.get_project(project.project_id)
    assert loaded.sample_ids == ["FCIP-03"]
    assert repository.get_sample(project.project_id, "FCIP-03").composition["matrix"] == "Paraffin"

    source.write_bytes(original + b"changed")
    assert repository.verify_measurement_sources(project.project_id, sample.sample_id, measurement.measurement_id) == {
        str(source.resolve()): "CHANGED"
    }


def test_analysis_runs_are_append_only_records(tmp_path):
    source = tmp_path / "pattern.txt"
    source.write_text("10, 1\n11, 2\n", encoding="utf-8")
    repository = WorkspaceRepository(tmp_path / "workspace")
    project = repository.create_project("XRD")
    sample = repository.create_sample(project.project_id, "A", sample_id="A")
    measurement = repository.add_measurement(project.project_id, sample.sample_id, "xrd", [source])

    first = repository.add_analysis_run(
        project.project_id,
        sample.sample_id,
        measurement.measurement_id,
        analysis_type="baseline",
        analysis_engine_version="1.0",
        parameters={"method": "A"},
    )
    second = repository.add_analysis_run(
        project.project_id,
        sample.sample_id,
        measurement.measurement_id,
        analysis_type="baseline",
        analysis_engine_version="1.0",
        parameters={"method": "B"},
        validation_status="WARNING",
        warnings=["review baseline"],
    )

    runs = repository.list_analysis_runs(project.project_id, sample.sample_id, measurement.measurement_id)
    assert {run.analysis_run_id for run in runs} == {first.analysis_run_id, second.analysis_run_id}
    assert {run.parameters["method"] for run in runs} == {"A", "B"}
    assert next(run for run in runs if run.analysis_run_id == second.analysis_run_id).warnings == ["review baseline"]


def test_duplicate_sample_id_and_missing_source_are_rejected(tmp_path):
    repository = WorkspaceRepository(tmp_path / "workspace")
    one = repository.create_project("one")
    two = repository.create_project("two")
    repository.create_sample(one.project_id, "sample", sample_id="FCIP-01")
    with pytest.raises(ValueError, match="样品 ID 已存在"):
        repository.create_sample(two.project_id, "duplicate", sample_id="FCIP-01")
    with pytest.raises(FileNotFoundError, match="原始文件不存在"):
        repository.add_measurement(one.project_id, "FCIP-01", "vsm", [tmp_path / "missing.dat"])


def test_workspace_page_creates_project_sample_and_measurement(qtbot, tmp_path):
    repository = WorkspaceRepository(tmp_path / "workspace")
    page = WorkspacePage(repository)
    qtbot.addWidget(page)
    project = page.create_project("综合表征")
    sample = page.create_sample("FCIP", sample_id="FCIP-02", material_system="CIP")
    source = tmp_path / "FCIP-02.memp"
    source.write_bytes(b"synthetic only")
    measurement = page.add_measurement("electromagnetic", [source])

    assert page.current_project_id == project.project_id
    assert page.current_sample_id == sample.sample_id
    assert page.samples.rowCount() == 1
    assert page.samples.item(0, 2).text() == "! PENDING"
    assert page.measurements.rowCount() == 1
    assert measurement.measurement_type == "electromagnetic"
