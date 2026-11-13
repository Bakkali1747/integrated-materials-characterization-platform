"""VSM 与工作区、GUI 的闭环：自动登记、不可计算状态、载入分发。"""

import math

import numpy as np

from core.common import ValidationStatus, WorkspaceRepository, link_vsm_run
from core.vsm_service import VSMConfig
from gui.controllers.vsm_controller import analyze_vsm_request
from gui.main_window import MainWindow
from gui.pages.vsm_page import VsmPage
from gui.pages.workspace_page import WorkspacePage


def write_loop(path, *, hc=100.0, ms=20.0, width=120.0, hmax=3000.0, step=60.0):
    up = np.arange(-hmax, hmax + step / 2, step)
    down = np.arange(hmax - step, -hmax - step / 2, -step)
    rows = ["field_oe,moment_emu"]
    rows += [f"{h},{0.01 * ms * math.tanh((h - hc) / width)}" for h in up]
    rows += [f"{h},{0.01 * ms * math.tanh((h + hc) / width)}" for h in down]
    path.write_text("\n".join(rows), encoding="utf-8")
    return path


def run_vsm(tmp_path, source, name="FCIP-VSM"):
    config = VSMConfig(path=source, name=name, output=tmp_path / "vsm-runs", mass_mg=10.0, dpi=40)
    return analyze_vsm_request(config)


def test_link_vsm_run_records_plot_refs_and_pending_status(tmp_path):
    source = write_loop(tmp_path / "loop.csv")
    result = run_vsm(tmp_path, source)
    repository = WorkspaceRepository(tmp_path / "workspace")
    project = repository.create_project("VSM")
    sample = repository.create_sample(project.project_id, "FCIP", sample_id="V1")
    measurement = repository.add_measurement(project.project_id, sample.sample_id, "vsm", [source])

    run = link_vsm_run(repository, project.project_id, sample.sample_id, measurement.measurement_id,
                       result["directory"], result["record"])

    assert run.analysis_type == "vsm_hysteresis"
    assert run.validation_status == ValidationStatus.PENDING.value
    assert run.parameters["mass_mg"] == 10.0
    assert any(ref.endswith("vsm_metrics.json") for ref in run.result_refs)
    assert len(run.plot_refs) == 2
    assert repository.get_measurement(project.project_id, sample.sample_id,
                                      measurement.measurement_id).validation_status == "PENDING"


def test_link_vsm_run_registers_not_computable_status(tmp_path):
    source = tmp_path / "positive.csv"
    source.write_text("field_oe,moment_emu\n" + "\n".join(
        f"{h},{0.01 * 20 * math.tanh((h - 100) / 120)}" for h in range(100, 3100, 100)),
        encoding="utf-8")
    result = run_vsm(tmp_path, source)
    assert result["record"]["status"] == "not_computable"
    repository = WorkspaceRepository(tmp_path / "workspace")
    project = repository.create_project("VSM")
    sample = repository.create_sample(project.project_id, "FCIP", sample_id="V2")
    measurement = repository.add_measurement(project.project_id, sample.sample_id, "vsm", [source])

    run = link_vsm_run(repository, project.project_id, sample.sample_id, measurement.measurement_id,
                       result["directory"], result["record"])

    assert run.validation_status == ValidationStatus.NOT_COMPUTABLE.value
    assert repository.get_measurement(project.project_id, sample.sample_id,
                                      measurement.measurement_id).validation_status == "NOT_COMPUTABLE"


def test_workspace_page_starts_and_records_vsm_analysis(qtbot, tmp_path):
    source = write_loop(tmp_path / "loop.csv")
    repository = WorkspaceRepository(tmp_path / "workspace")
    page = WorkspacePage(repository)
    qtbot.addWidget(page)
    project = page.create_project("VSM GUI")
    sample = page.create_sample("FCIP", sample_id="V3")
    measurement = page.add_measurement("vsm", [source])

    assert page.vsm_button.isEnabled()
    assert not page.analyze_button.isEnabled()
    assert not page.sparameter_button.isEnabled()
    with qtbot.waitSignal(page.vsm_analysis_requested) as signal:
        request = page.start_measurement_vsm_analysis()
    assert request == signal.args[0]
    assert request["kind"] == "vsm_hysteresis"

    result = run_vsm(tmp_path, source)
    page.record_vsm_run(project.project_id, sample.sample_id, measurement.measurement_id,
                        result["directory"], result["record"])
    assert page.runs.rowCount() == 1
    assert page.runs.item(0, 1).text() == "VSM 磁滞回线"
    assert page.samples.item(0, 3).text() == "! PENDING"


def test_main_window_registers_vsm_run_and_dispatches_loading(qtbot, tmp_path, monkeypatch):
    repository = WorkspaceRepository(tmp_path / "workspace")
    window = MainWindow(workspace_repository=repository)
    qtbot.addWidget(window)
    project = window.workspace.create_project("VSM 主窗口")
    sample = window.workspace.create_sample("FCIP", sample_id="V4")
    source = write_loop(tmp_path / "loop.csv")
    measurement = window.workspace.add_measurement("vsm", [source])

    window.workspace.start_measurement_vsm_analysis()
    assert window.navigation.currentRow() == 3
    assert window.pending_workspace_analysis["kind"] == "vsm_hysteresis"
    assert window.vsm.file.text() == str(source)

    result = run_vsm(tmp_path, source)
    run = window.record_workspace_vsm_run({"directory": result["directory"], "record": result["record"]})
    assert run is not None
    assert window.pending_workspace_analysis is None
    assert repository.list_analysis_runs(project.project_id, sample.sample_id,
                                         measurement.measurement_id)[0].analysis_run_id == run.analysis_run_id

    calls = []
    monkeypatch.setattr(window.vsm, "open_completed_run", lambda directory: calls.append(("vsm", directory)))
    monkeypatch.setattr(window.sparameters, "open_completed_run", lambda directory: calls.append(("s", directory)))
    monkeypatch.setattr(window.single, "open_completed_run", lambda directory: calls.append(("em", directory)))
    window.open_workspace_run({"directory": "v-dir", "analysis_type": "vsm_hysteresis"})
    assert window.navigation.currentRow() == 3
    window.open_workspace_run({"directory": "s-dir", "analysis_type": "s_parameters"})
    assert window.navigation.currentRow() == 4 and window.ui_mode == "full"
    window.open_workspace_run({"directory": "e-dir"})
    assert window.navigation.currentRow() == 2
    assert calls == [("vsm", "v-dir"), ("s", "s-dir"), ("em", "e-dir")]


def test_vsm_page_runs_and_reloads_saved_result(qtbot, tmp_path):
    source = write_loop(tmp_path / "loop.csv")
    page = VsmPage()
    qtbot.addWidget(page)
    page.export_dpi = 60
    page.file.setText(str(source))
    page.name.setText("FCIP")
    page.output.setText(str(tmp_path / "out"))
    page.mass.setText("10")
    page.load_columns()
    assert page.field_column.currentText().casefold().startswith("field")
    assert page.moment_column.currentText().casefold().startswith("moment")

    page.start_analysis()
    qtbot.waitUntil(lambda: not page.busy, timeout=60000)
    assert page.completed is not None, page.error.text()
    assert page.completed["metrics"]["Hc_oe"] is not None
    assert page.plot.selector.count() == 2
    assert page.metrics.rowCount() > 0

    directory = page.completed["directory"]
    assert page.open_completed_run(directory)
    assert page.completed["directory"] == directory
    assert page.plot.selector.count() == 2
