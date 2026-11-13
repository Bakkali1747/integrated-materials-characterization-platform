"""XRD 与工作区、GUI 的闭环：自动登记、不可计算状态、载入分发。"""

import numpy as np

from core.common import ValidationStatus, WorkspaceRepository, link_xrd_run
from core.xrd_service import XRDConfig
from gui.controllers.xrd_controller import analyze_xrd_request
from gui.main_window import MainWindow
from gui.pages.workspace_page import WorkspacePage
from gui.pages.xrd_page import XrdPage


def write_pattern(path, peaks=((20.0, 500.0, .08), (30.0, 300.0, .10), (40.0, 200.0, .12))):
    x = np.arange(10.0, 80.01, .02)
    y = 100.0 + 0.5 * x
    for position, amplitude, sigma in peaks:
        y = y + amplitude * np.exp(-((x - position) / sigma) ** 2)
    path.write_text("two_theta_deg,intensity\n" + "\n".join(f"{a:.4f},{b:.6f}" for a, b in zip(x, y)),
                    encoding="utf-8")
    return path


def run_xrd(tmp_path, source, name="FCIP-XRD"):
    return analyze_xrd_request(XRDConfig(path=source, name=name, output=tmp_path / "xrd-runs",
                                         dpi=40, wavelength_angstrom=1.5406,
                                         min_prominence_relative=.01))


def test_link_xrd_run_records_peaks_and_status(tmp_path):
    source = write_pattern(tmp_path / "pattern.csv")
    result = run_xrd(tmp_path, source)
    repository = WorkspaceRepository(tmp_path / "workspace")
    project = repository.create_project("XRD")
    sample = repository.create_sample(project.project_id, "FCIP", sample_id="X1")
    measurement = repository.add_measurement(project.project_id, sample.sample_id, "xrd", [source])

    run = link_xrd_run(repository, project.project_id, sample.sample_id, measurement.measurement_id,
                       result["directory"], result["record"])

    assert run.analysis_type == "xrd_peaks"
    assert run.validation_status == ValidationStatus.PENDING.value
    assert run.parameters["wavelength_angstrom"] == 1.5406
    assert any(ref.endswith("xrd_peaks.json") for ref in run.result_refs)
    assert len(run.plot_refs) == 1
    assert repository.get_measurement(project.project_id, sample.sample_id,
                                      measurement.measurement_id).validation_status == "PENDING"


def test_workspace_page_starts_and_records_xrd_analysis(qtbot, tmp_path):
    source = write_pattern(tmp_path / "pattern.csv")
    repository = WorkspaceRepository(tmp_path / "workspace")
    page = WorkspacePage(repository)
    qtbot.addWidget(page)
    project = page.create_project("XRD GUI")
    sample = page.create_sample("FCIP", sample_id="X2")
    measurement = page.add_measurement("xrd", [source])

    assert page.xrd_button.isEnabled()
    assert not page.analyze_button.isEnabled()
    with qtbot.waitSignal(page.xrd_analysis_requested) as signal:
        request = page.start_measurement_xrd_analysis()
    assert request == signal.args[0]
    assert request["kind"] == "xrd_peaks"

    result = run_xrd(tmp_path, source)
    page.record_xrd_run(project.project_id, sample.sample_id, measurement.measurement_id,
                        result["directory"], result["record"])
    assert page.runs.rowCount() == 1
    assert page.runs.item(0, 1).text() == "XRD 峰分析"
    assert page.samples.item(0, 4).text() == "! PENDING"


def test_main_window_registers_xrd_run_and_dispatches_loading(qtbot, tmp_path, monkeypatch):
    repository = WorkspaceRepository(tmp_path / "workspace")
    window = MainWindow(workspace_repository=repository)
    qtbot.addWidget(window)
    project = window.workspace.create_project("XRD 主窗口")
    sample = window.workspace.create_sample("FCIP", sample_id="X3")
    source = write_pattern(tmp_path / "pattern.csv")
    measurement = window.workspace.add_measurement("xrd", [source])

    window.workspace.start_measurement_xrd_analysis()
    assert window.navigation.currentRow() == 4
    assert window.pending_workspace_analysis["kind"] == "xrd_peaks"
    assert window.xrd.file.text() == str(source)
    assert window.xrd.two_theta_column.currentText() == "two_theta_deg"

    result = run_xrd(tmp_path, source)
    run = window.record_workspace_xrd_run({"directory": result["directory"], "record": result["record"]})
    assert run is not None
    assert window.pending_workspace_analysis is None
    assert repository.list_analysis_runs(project.project_id, sample.sample_id,
                                         measurement.measurement_id)[0].analysis_run_id == run.analysis_run_id

    calls = []
    monkeypatch.setattr(window.xrd, "open_completed_run", lambda directory: calls.append(("xrd", directory)))
    monkeypatch.setattr(window.vsm, "open_completed_run", lambda directory: calls.append(("vsm", directory)))
    window.open_workspace_run({"directory": "x-dir", "analysis_type": "xrd_peaks"})
    assert window.navigation.currentRow() == 4
    window.open_workspace_run({"directory": "v-dir", "analysis_type": "vsm_hysteresis"})
    assert window.navigation.currentRow() == 3
    assert calls == [("xrd", "x-dir"), ("vsm", "v-dir")]


def test_xrd_page_runs_and_reloads_saved_result(qtbot, tmp_path):
    source = write_pattern(tmp_path / "pattern.csv")
    page = XrdPage()
    qtbot.addWidget(page)
    page.export_dpi = 60
    page.file.setText(str(source))
    page.name.setText("FCIP")
    page.output.setText(str(tmp_path / "out"))
    page.load_columns()
    assert page.two_theta_column.currentText() == "two_theta_deg"
    assert page.intensity_column.currentText() == "intensity"
    page.start_analysis()
    qtbot.waitUntil(lambda: not page.busy, timeout=60000)
    assert page.completed is not None, page.error.text()
    assert len(page.completed["metrics"]["peaks"]) == 3
    assert page.plot.selector.count() == 1
    assert page.peaks.rowCount() == 3

    directory = page.completed["directory"]
    assert page.open_completed_run(directory)
    assert page.completed["directory"] == directory
    assert page.peaks.rowCount() == 3
