"""Phase A 项目、样品、测试和分析运行工作区，以及 Phase B 电磁分析接入。"""

import hashlib
import json
from pathlib import Path

import pytest

from core.common import (
    MeasurementType,
    ValidationStatus,
    WorkspaceRepository,
    analysis_run_status,
    link_electromagnetic_run,
    link_sparameter_run,
)
from gui.main_window import MainWindow
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
    assert "schema v" in page.schema_label.text()


def _completed_run(directory: Path, source: Path, *, warnings=(), status="success") -> dict:
    """构造一份已完成运行的记录与最小产物，只用于登记逻辑，不代表真实数值结果。"""
    directory.mkdir(parents=True, exist_ok=True)
    figures = directory / "figures"
    figures.mkdir()
    (figures / "RL_curve.png").write_bytes(b"synthetic png")
    (directory / "summary.json").write_text("{}", encoding="utf-8")
    (directory / "thickness_summary.csv").write_text("thickness_mm\n1\n", encoding="utf-8")
    return {
        "status": status,
        "sample": source.stem,
        "raw_file": str(source.resolve()),
        "raw_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "software_version": "0.14.0",
        "analysis_cache_version": 1,
        "git": {"commit": "abc123", "dirty": False},
        "configuration": {"thickness_step_mm": 0.1, "rl_threshold_db": -10.0,
                          "curve_thickness_mm": 1.0},
        "warnings": list(warnings),
    }


def _electromagnetic_sample(repository, tmp_path):
    source = tmp_path / "FCIP-03.csv"
    source.write_text("frequency_ghz,eps_real,eps_imag,mu_real,mu_imag\n2,4,.2,1.5,.3\n4,4.2,.3,1.3,.5\n",
                      encoding="utf-8")
    project = repository.create_project("Phase B")
    sample = repository.create_sample(project.project_id, "FCIP", sample_id="FCIP-03")
    measurement = repository.add_measurement(project.project_id, sample.sample_id, "electromagnetic", [source])
    return source, project, sample, measurement


def test_analysis_run_status_never_becomes_validated():
    assert analysis_run_status({"status": "success", "warnings": []}) is ValidationStatus.PENDING
    assert analysis_run_status({"status": "success", "warnings": ["[KNOWN] 边界"]}) is ValidationStatus.WARNING
    with pytest.raises(ValueError, match="成功完成"):
        analysis_run_status({"status": "failed", "warnings": []})


def test_link_electromagnetic_run_records_refs_and_measurement_status(tmp_path):
    repository = WorkspaceRepository(tmp_path / "workspace")
    source, project, sample, measurement = _electromagnetic_sample(repository, tmp_path)
    directory = tmp_path / "output" / "synthetic" / "run-1"
    record = _completed_run(directory, source, warnings=["[KNOWN] 网格最小值触及边界"])

    run = link_electromagnetic_run(repository, project.project_id, sample.sample_id,
                                   measurement.measurement_id, directory, record)

    assert run.analysis_type == "electromagnetic_rl"
    assert run.validation_status == ValidationStatus.WARNING.value
    assert run.parameters["thickness_step_mm"] == 0.1
    assert run.result_refs[0] == str(directory.resolve())
    assert any(ref.endswith("summary.json") for ref in run.result_refs)
    assert run.plot_refs == [str((directory / "figures" / "RL_curve.png").resolve())]
    assert run.errors == [] and run.warnings == ["[KNOWN] 网格最小值触及边界"]
    assert run.source_sha256 == measurement.source_sha256

    reloaded = repository.get_measurement(project.project_id, sample.sample_id, measurement.measurement_id)
    assert reloaded.validation_status == ValidationStatus.WARNING.value
    assert [item.analysis_run_id for item in repository.list_analysis_runs(
        project.project_id, sample.sample_id, measurement.measurement_id)] == [run.analysis_run_id]


def test_link_rejects_changed_source_hash_without_writing_run(tmp_path):
    repository = WorkspaceRepository(tmp_path / "workspace")
    source, project, sample, measurement = _electromagnetic_sample(repository, tmp_path)
    directory = tmp_path / "run"
    record = _completed_run(directory, source)
    record["raw_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="SHA-256"):
        link_electromagnetic_run(repository, project.project_id, sample.sample_id,
                                 measurement.measurement_id, directory, record)
    assert repository.list_analysis_runs(project.project_id, sample.sample_id, measurement.measurement_id) == []
    assert repository.get_measurement(project.project_id, sample.sample_id,
                                      measurement.measurement_id).validation_status == "PENDING"


def test_link_rejects_non_electromagnetic_measurement(tmp_path):
    source = tmp_path / "pattern.txt"
    source.write_text("10,1\n", encoding="utf-8")
    repository = WorkspaceRepository(tmp_path / "workspace")
    project = repository.create_project("XRD")
    sample = repository.create_sample(project.project_id, "A", sample_id="A")
    measurement = repository.add_measurement(project.project_id, sample.sample_id, "xrd", [source])
    directory = tmp_path / "run"
    record = _completed_run(directory, source)

    with pytest.raises(ValueError, match="Electromagnetic"):
        link_electromagnetic_run(repository, project.project_id, sample.sample_id,
                                 measurement.measurement_id, directory, record)


def _completed_sparameter_run(directory: Path, source: Path, *, warnings=()) -> dict:
    """构造 S 参数完成记录与最小产物；QC 警告保存在 quality_checks 中。"""
    directory.mkdir(parents=True, exist_ok=True)
    figures = directory / "figures"
    figures.mkdir()
    (figures / "SE.png").write_bytes(b"synthetic png")
    (directory / "sparameters_by_frequency.csv").write_text("frequency_ghz\n2\n", encoding="utf-8")
    (directory / "quality_checks.json").write_text(json.dumps({"warnings": list(warnings)}), encoding="utf-8")
    return {
        "status": "success",
        "sample": source.stem,
        "raw_file": str(source.resolve()),
        "raw_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "software_version": "0.15.0",
        "source": {"parser": "sdat-v1"},
        "schema_status": "candidate_high_confidence",
        "mapping": {"schema_id": "candidate", "schema_status": "candidate_high_confidence"},
        "tolerances": {"magnitude_atol": 1e-6},
        "quality_checks": {"warnings": list(warnings)},
        "git": {"commit": "abc123", "dirty": False},
    }


def _sparameter_sample(repository, tmp_path):
    source = tmp_path / "FCIP-10.sdat"
    source.write_bytes(b"synthetic candidate sdat; not a manufacturer file")
    project = repository.create_project("S parameters")
    sample = repository.create_sample(project.project_id, "FCIP", sample_id="FCIP-10")
    measurement = repository.add_measurement(project.project_id, sample.sample_id, "electromagnetic", [source])
    return source, project, sample, measurement


def test_link_sparameter_run_records_candidate_parameters(tmp_path):
    repository = WorkspaceRepository(tmp_path / "workspace")
    source, project, sample, measurement = _sparameter_sample(repository, tmp_path)
    directory = tmp_path / "sp-runs" / "run-1"
    record = _completed_sparameter_run(directory, source)

    run = link_sparameter_run(repository, project.project_id, sample.sample_id,
                              measurement.measurement_id, directory, record)

    assert run.analysis_type == "s_parameters"
    assert run.validation_status == ValidationStatus.PENDING.value
    assert run.parameters["schema_status"] == "candidate_high_confidence"
    assert run.parameters["tolerances"]["magnitude_atol"] == 1e-6
    assert run.analysis_engine_version == "0.15.0/sdat-v1"
    assert any(ref.endswith("sparameters_by_frequency.csv") for ref in run.result_refs)
    assert run.plot_refs == [str((directory / "figures" / "SE.png").resolve())]
    assert run.warnings == []
    assert repository.get_measurement(project.project_id, sample.sample_id,
                                      measurement.measurement_id).validation_status == "PENDING"


def test_link_sparameter_run_surfaces_qc_warnings_as_warning_status(tmp_path):
    repository = WorkspaceRepository(tmp_path / "workspace")
    source, project, sample, measurement = _sparameter_sample(repository, tmp_path)
    directory = tmp_path / "sp-runs" / "run-2"
    warning = "[COMPUTED] A 有 2 个负值，包括容差内轻微负值；未 clip。"
    record = _completed_sparameter_run(directory, source, warnings=[warning])

    run = link_sparameter_run(repository, project.project_id, sample.sample_id,
                              measurement.measurement_id, directory, record)

    assert run.validation_status == ValidationStatus.WARNING.value
    assert run.warnings == [warning]
    assert repository.get_measurement(project.project_id, sample.sample_id,
                                      measurement.measurement_id).validation_status == "WARNING"


def test_link_sparameter_run_rejects_changed_source(tmp_path):
    repository = WorkspaceRepository(tmp_path / "workspace")
    source, project, sample, measurement = _sparameter_sample(repository, tmp_path)
    directory = tmp_path / "sp-runs" / "run-3"
    record = _completed_sparameter_run(directory, source)
    record["raw_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="SHA-256"):
        link_sparameter_run(repository, project.project_id, sample.sample_id,
                            measurement.measurement_id, directory, record)
    assert repository.list_analysis_runs(project.project_id, sample.sample_id, measurement.measurement_id) == []


def test_workspace_page_starts_and_records_electromagnetic_analysis(qtbot, tmp_path, frame):
    repository = WorkspaceRepository(tmp_path / "workspace")
    page = WorkspacePage(repository)
    qtbot.addWidget(page)
    project = page.create_project("Phase B GUI")
    sample = page.create_sample("FCIP", sample_id="FCIP-04")
    source = tmp_path / "FCIP-04.csv"
    frame.to_csv(source, index=False)
    measurement = page.add_measurement("electromagnetic", [source])

    with qtbot.waitSignal(page.analysis_requested) as signal:
        request = page.start_measurement_analysis()
    assert request == signal.args[0]
    assert request["measurement_id"] == measurement.measurement_id
    assert Path(request["path"]) == source.resolve()

    first = tmp_path / "run-1"
    page.record_electromagnetic_run(project.project_id, sample.sample_id, measurement.measurement_id,
                                    first, _completed_run(first, source))
    assert page.runs.rowCount() == 1
    assert page.samples.item(0, 2).text() == "! PENDING"
    assert repository.get_measurement(project.project_id, sample.sample_id,
                                      measurement.measurement_id).validation_status == "PENDING"

    second = tmp_path / "run-2"
    page.record_electromagnetic_run(project.project_id, sample.sample_id, measurement.measurement_id,
                                    second, _completed_run(second, source, warnings=["[KNOWN] 边界"]))
    assert page.runs.rowCount() == 2
    assert page.samples.item(0, 2).text() == "⚠ Warning"
    assert repository.get_measurement(project.project_id, sample.sample_id,
                                      measurement.measurement_id).validation_status == "WARNING"

    exported = tmp_path / "export" / "RL_curve.png"
    exported.parent.mkdir()
    exported.write_bytes(b"png")
    updated = page.record_exports(second, [exported])
    assert updated is not None and str(exported.resolve()) in updated.export_refs
    assert str(exported.resolve()) in repository.find_analysis_run_by_result_directory(second)[2].export_refs


def test_workspace_page_selects_the_newly_added_measurement(qtbot, tmp_path):
    repository = WorkspaceRepository(tmp_path / "workspace")
    page = WorkspacePage(repository)
    qtbot.addWidget(page)
    page.create_project("多个测试")
    page.create_sample("FCIP", sample_id="FCIP-13")
    csv_source = tmp_path / "FCIP-13.csv"
    csv_source.write_text("frequency_ghz,eps_real,eps_imag,mu_real,mu_imag\n2,4,.2,1.5,.3\n", encoding="utf-8")
    sdat_source = tmp_path / "FCIP-13.sdat"
    sdat_source.write_bytes(b"synthetic candidate sdat")

    page.add_measurement("electromagnetic", [csv_source])
    second = page.add_measurement("electromagnetic", [sdat_source])

    assert page.current_measurement_id == second.measurement_id
    assert page.sparameter_button.isEnabled()
    assert not page.analyze_button.isEnabled()


def test_workspace_page_starts_and_records_sparameter_analysis(qtbot, tmp_path):
    repository = WorkspaceRepository(tmp_path / "workspace")
    page = WorkspacePage(repository)
    qtbot.addWidget(page)
    project = page.create_project("S 参数 GUI")
    sample = page.create_sample("FCIP", sample_id="FCIP-11")
    source = tmp_path / "FCIP-11.sdat"
    source.write_bytes(b"synthetic candidate sdat")
    measurement = page.add_measurement("electromagnetic", [source])

    assert not page.analyze_button.isEnabled()
    assert page.sparameter_button.isEnabled()
    with qtbot.waitSignal(page.sparameter_analysis_requested) as signal:
        request = page.start_measurement_sparameter_analysis()
    assert request == signal.args[0]
    assert request["kind"] == "s_parameters"
    assert Path(request["path"]) == source.resolve()

    directory = tmp_path / "sp-run"
    page.record_sparameter_run(project.project_id, sample.sample_id, measurement.measurement_id,
                               directory, _completed_sparameter_run(directory, source))
    assert page.runs.rowCount() == 1
    assert page.runs.item(0, 1).text() == "S 参数分析"
    assert repository.get_measurement(project.project_id, sample.sample_id,
                                      measurement.measurement_id).validation_status == "PENDING"


def test_main_window_registers_completed_workspace_analysis(qtbot, tmp_path, frame):
    repository = WorkspaceRepository(tmp_path / "workspace")
    window = MainWindow(workspace_repository=repository)
    qtbot.addWidget(window)
    project = window.workspace.create_project("Phase B 主窗口")
    sample = window.workspace.create_sample("FCIP", sample_id="FCIP-05")
    source = tmp_path / "FCIP-05.csv"
    frame.to_csv(source, index=False)
    measurement = window.workspace.add_measurement("electromagnetic", [source])

    window.workspace.start_measurement_analysis()
    assert window.navigation.currentRow() == 2
    assert window.pending_workspace_analysis["measurement_id"] == measurement.measurement_id
    qtbot.waitUntil(lambda: not window.single.busy, timeout=30000)

    directory = tmp_path / "run"
    run = window.record_workspace_analysis({"directory": directory, "record": _completed_run(directory, source)})
    assert run is not None
    assert window.pending_workspace_analysis is None
    assert repository.list_analysis_runs(project.project_id, sample.sample_id,
                                         measurement.measurement_id)[0].analysis_run_id == run.analysis_run_id

    window.pending_workspace_analysis = {"kind": "electromagnetic_rl", "project_id": project.project_id,
                                         "sample_id": sample.sample_id,
                                         "measurement_id": measurement.measurement_id,
                                         "path": str(tmp_path / "other.csv")}
    other = tmp_path / "other-run"
    assert window.record_workspace_analysis(
        {"directory": other, "record": _completed_run(other, source)}) is None
    assert window.pending_workspace_analysis is None


def test_main_window_registers_workspace_sparameter_run_and_exports(qtbot, tmp_path):
    repository = WorkspaceRepository(tmp_path / "workspace")
    window = MainWindow(workspace_repository=repository)
    qtbot.addWidget(window)
    project = window.workspace.create_project("S 参数主窗口")
    sample = window.workspace.create_sample("FCIP", sample_id="FCIP-12")
    source = tmp_path / "FCIP-12.sdat"
    source.write_bytes(b"synthetic candidate sdat")
    measurement = window.workspace.add_measurement("electromagnetic", [source])

    window.workspace.start_measurement_sparameter_analysis()
    assert window.navigation.currentRow() == 5
    assert window.pending_workspace_analysis["kind"] == "s_parameters"
    assert window.pending_workspace_analysis["measurement_id"] == measurement.measurement_id
    assert window.sparameters.file.text() == str(source)
    assert window.ui_mode == "full"

    directory = tmp_path / "sp-run"
    run = window.record_workspace_sparameter_run(
        {"directory": directory, "record": _completed_sparameter_run(directory, source)})
    assert run is not None and run.analysis_type == "s_parameters"
    assert window.pending_workspace_analysis is None
    assert repository.list_analysis_runs(project.project_id, sample.sample_id,
                                         measurement.measurement_id)[0].analysis_run_id == run.analysis_run_id

    exported = tmp_path / "exports" / "SE.png"
    exported.parent.mkdir()
    exported.write_bytes(b"png")
    window.sparameters.exports_saved.emit({"directory": str(directory), "paths": [str(exported)]})
    linked = repository.find_analysis_run_by_result_directory(directory)[2]
    assert str(exported.resolve()) in linked.export_refs


def test_workspace_analysis_run_export_refs_are_deduplicated(tmp_path):
    repository = WorkspaceRepository(tmp_path / "workspace")
    source, project, sample, measurement = _electromagnetic_sample(repository, tmp_path)
    directory = tmp_path / "run"
    run = link_electromagnetic_run(repository, project.project_id, sample.sample_id,
                                   measurement.measurement_id, directory, _completed_run(directory, source))
    image = tmp_path / "image.png"
    image.write_bytes(b"png")
    repository.add_analysis_run_export_refs(project.project_id, sample.sample_id, run.analysis_run_id, [image, image])
    reloaded = repository.list_analysis_runs(project.project_id, sample.sample_id, measurement.measurement_id)[0]
    assert reloaded.export_refs == [str(image.resolve())]
    assert json.loads((tmp_path / "workspace" / "projects" / project.project_id / "samples" / sample.sample_id
                       / "analyses" / f"{run.analysis_run_id}.json").read_text(encoding="utf-8"))["export_refs"] == [
        str(image.resolve())]

