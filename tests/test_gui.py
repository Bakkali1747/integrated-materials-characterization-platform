"""GUI 流程/信号/科学 API 等价性测试；不比较像素。"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from gui.controllers.analysis_controller import AnalysisRequest, Cancelled, analyze_request, inspect_file
from gui.controllers.export_controller import export_figure
from gui.main_window import MainWindow
from gui.pages.single_sample_page import SingleSamplePage
from gui.widgets.file_selector import FileSelector
from gui.widgets.parameter_panel import ParameterPanel
from gui.widgets.sample_table import SampleTable
from gui.widgets.status_badge import StatusBadge
from gui.workers.analysis_worker import AnalysisWorker


@pytest.fixture
def source(tmp_path, frame):
    path = tmp_path / "synthetic.csv"
    frame.to_csv(path, index=False)
    return path


@pytest.fixture
def window(qtbot):
    widget = MainWindow()
    qtbot.addWidget(widget)
    widget.show()
    yield widget
    if widget.single.worker:
        widget.single.worker.requestInterruption()
        qtbot.waitUntil(lambda: not widget.single.busy, timeout=30000)


@pytest.fixture
def result(source, tmp_path):
    return analyze_request(AnalysisRequest(source, "synthetic", output=tmp_path / "output", thickness_max=1.1, thickness_step=.1, dpi=30))


def test_main_window_start_and_navigation(window, qtbot):
    assert window.minimumWidth() == 1200
    assert window.minimumHeight() == 750
    assert "综合材料表征分析平台" in window.windowTitle()
    window.navigation.setCurrentRow(1)
    assert window.stack.currentWidget() is window.workspace
    window.navigation.setCurrentRow(2)
    assert window.stack.currentWidget() is window.single
    window.navigation.setCurrentRow(3)
    assert "S 参数" in window.stack.currentWidget().text()


def test_file_dialog_multiselect(qtbot, monkeypatch, source):
    selector = FileSelector()
    qtbot.addWidget(selector)
    monkeypatch.setattr("gui.widgets.file_selector.QFileDialog.getOpenFileNames", lambda *args: ([str(source)], ""))
    with qtbot.waitSignal(selector.files_selected) as signal:
        selector.files_button.click()
    assert signal.args[0] == [str(source)]


def test_directory_dialog(qtbot, monkeypatch, tmp_path):
    selector = FileSelector()
    qtbot.addWidget(selector)
    monkeypatch.setattr("gui.widgets.file_selector.QFileDialog.getExistingDirectory", lambda *args: str(tmp_path))
    with qtbot.waitSignal(selector.files_selected) as signal:
        selector.folder_button.click()
    assert signal.args[0] == [str(tmp_path)]


def test_import_source_information(window, source, qtbot):
    window.single.import_paths([source])
    qtbot.waitUntil(lambda: not window.single.busy)
    info = window.single.selected
    assert info["points"] == 3
    assert info["frequency"] == (2., 4.)
    assert info["status"] == "PENDING"
    assert info["size"] == source.stat().st_size
    assert window.single.start_button.isEnabled()


def test_unsupported_format_message(window, tmp_path, qtbot):
    path = tmp_path / "bad.txt"
    path.write_text("bad")
    window.single.import_paths([path])
    qtbot.waitUntil(lambda: not window.single.busy)
    assert window.single.selected["status"] == "FAIL"
    assert "不支持" in window.single.error.text()
    assert not window.single.start_button.isEnabled()


def test_single_reuse_returns_completed_run(tmp_path, frame):
    path = tmp_path / "reuse.csv"
    frame.to_csv(path, index=False)
    request = AnalysisRequest(path, "reuse", output=tmp_path / "out", thickness_max=1.1,
                              thickness_step=.1, dpi=25, full_science=True, reuse=True)
    first = analyze_request(request)
    second = analyze_request(request)
    assert second["directory"] == first["directory"]
    assert second["result"].rl_db.shape == first["result"].rl_db.shape
    assert second["figures"] and all(figure is None for figure in second["figures"].values())
    assert second["summary"]["standard_eab"] == first["summary"]["standard_eab"]


def test_parameter_snapshot_and_no_automatic_analysis(window, source, qtbot):
    panel = window.single.parameters
    panel.name.setText("CIP")
    panel.fields["thickness_step"].setValue(.02)
    request = panel.request(source)
    assert request.thickness_min == 1 and request.thickness_max == 5
    assert request.thickness_step == .02 and request.threshold == -10
    assert request.frequency_min is None
    assert request.parser_options["convention_confirmed"] is False
    assert request.eab_crossing == "linear" and request.quarter_wave_orders == (1,)
    assert request.impedance_tolerance == .1
    assert window.single.worker is None


def test_advanced_analysis_parameters(qtbot, source):
    panel = ParameterPanel()
    qtbot.addWidget(panel)
    panel.name.setText("CIP")
    panel.eab_crossing.setCurrentIndex(panel.eab_crossing.findData("sample"))
    panel.quarter_orders.setText("1, 3，5")
    panel.impedance_tolerance.setValue(.2)
    request = panel.request(source)
    assert request.eab_crossing == "sample"
    assert request.quarter_wave_orders == (1, 3, 5)
    assert request.impedance_tolerance == .2
    panel.quarter_orders.setText("2")
    with pytest.raises(ValueError, match="正奇数"):
        panel.request(source)


def test_mapping_and_crop(qtbot, source):
    panel = ParameterPanel()
    qtbot.addWidget(panel)
    panel.name.setText("CIP")
    panel.crop.setChecked(True)
    panel.mapping.setText('{"frequency_ghz":"Frequency"}')
    assert panel.request(source).parser_options["column_map"]["frequency_ghz"] == "Frequency"
    assert panel.request(source).frequency_min == 2
    assert "column_map" not in panel.parser_options(Path("input.memp"))


def test_empty_output_rejected(qtbot, source):
    panel = ParameterPanel()
    qtbot.addWidget(panel)
    panel.output.clear()
    with pytest.raises(ValueError, match="输出目录"):
        panel.request(source)


def test_table_pairing_and_separate_sources(qtbot, source):
    table = SampleTable()
    qtbot.addWidget(table)
    info = inspect_file(source, {"imaginary_convention": "loss"})
    one = table.add_source(info)
    other = dict(info, path=source.with_suffix(".sdat"), format=".sdat", status="candidate_high_confidence")
    two = table.add_source(other)
    assert one.parent() is two.parent()
    assert len(table.sources) == 2
    table.add_source(dict(info, path=source.parent / "other" / source.name))
    assert table.topLevelItemCount() == 2
    with qtbot.waitSignal(table.source_selected) as signal:
        table.setCurrentItem(two)
    assert signal.args[0]["format"] == ".sdat"


@pytest.mark.parametrize("status", ["candidate_high_confidence", "PENDING", "WARNING"])
def test_candidate_badge_not_green(qtbot, status):
    badge = StatusBadge(status, "待验证")
    qtbot.addWidget(badge)
    assert "#fffbeb" in badge.styleSheet().lower()
    assert "Validated" not in badge.text()


def test_sdat_cannot_trigger_rl(window, source):
    info = inspect_file(source, {"imaginary_convention": "loss"})
    window.single.select_source(dict(info, format=".sdat", status="candidate_high_confidence"))
    assert not window.single.start_button.isEnabled()
    window.single.start_analysis()
    assert window.single.worker is None
    assert "Measured S Parameters" in window.single.badge.text()


def test_worker_progress_and_result(qtbot):
    def operation(progress, cancelled):
        progress(50, "阶段完成")
        return 12
    worker = AnalysisWorker(operation)
    signals = []
    worker.progress.connect(lambda n, text: signals.append((n, text)))
    with qtbot.waitSignal(worker.succeeded) as signal:
        worker.start()
    worker.wait()
    assert signal.args == [12]
    assert signals == [(50, "阶段完成")]


def test_worker_error_logs_traceback(qtbot, caplog):
    def operation(*args):
        raise ValueError("mu_imag 缺失，3 GHz")
    worker = AnalysisWorker(operation)
    with qtbot.waitSignal(worker.failed) as signal:
        worker.start()
    worker.wait()
    assert "3 GHz" in signal.args[0]
    assert "Traceback" not in signal.args[0]
    assert "Traceback" in caplog.text


def test_analysis_button_runs_off_main_thread(window, source, qtbot, monkeypatch, result):
    from PySide6.QtCore import QThread

    import gui.pages.single_sample_page as module
    info = inspect_file(source, {"imaginary_convention": "loss"})
    window.single.select_source(info)
    threads = []
    def analyze(request, progress, cancelled):
        threads.append(QThread.currentThread())
        progress(100, "完成")
        return result
    monkeypatch.setattr(module, "analyze_request", analyze)
    with qtbot.waitSignal(window.single.analysis_completed):
        window.single.start_button.click()
    qtbot.waitUntil(lambda: not window.single.busy)
    assert threads[0] != window.thread()
    assert "Maximum EAB" in window.single.summary.toPlainText()
    assert window.single.plot.selector.count() == 4
    window.single.plot.selector.setCurrentIndex(3)
    assert len(window.single.plot.canvas.figure.axes) == 2


def test_controller_matches_cli(source, tmp_path, result):
    from plotting.style import PlotStyle
    from run_analysis import analyze
    directory = analyze(source, output=tmp_path / "cli", name="synthetic", imaginary_convention="loss",
                        thickness_max=1.1, thickness_step=.1, style=PlotStyle(dpi=30))
    expected = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    assert result["summary"]["global_minima"] == expected["global_minima"]
    assert result["summary"]["standard_eab"] == expected["standard_eab"]
    assert result["summary"]["cumulative_frequency_coverage"] == expected["cumulative_frequency_coverage"]
    gui_table = pd.read_csv(result["directory"] / "thickness_summary.csv")
    cli_table = pd.read_csv(directory / "thickness_summary.csv")
    assert list(gui_table.columns) == list(cli_table.columns)
    np.testing.assert_array_equal(pd.read_csv(directory / "RL_matrix.csv").to_numpy(),
                                  pd.read_csv(result["directory"] / "RL_matrix.csv").to_numpy())


def test_provenance_output_and_original_unchanged(source, result):
    record = result["record"]
    assert record["status"] == "success"
    assert record["raw_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert record["missing_data_interpolation"] == "OFF"
    assert "parser_version" in record and "software_version" in record
    assert record["sdat_schema_status"] == "not_applicable"
    assert record["validation_status"].startswith("pending")
    assert record["frequency_points"] == 3
    for name, digest in record["artifacts_sha256"].items():
        assert hashlib.sha256((result["directory"] / name).read_bytes()).hexdigest() == digest


def test_invalid_parameters_do_not_create_run(source, tmp_path):
    with pytest.raises(ValueError):
        analyze_request(AnalysisRequest(source, "bad", output=tmp_path / "fail", thickness_min=5, thickness_max=1))
    assert not (tmp_path / "fail").exists()


def test_failure_record_after_validation(tmp_path):
    with pytest.raises(Exception):
        analyze_request(AnalysisRequest(tmp_path / "missing.csv", "bad", output=tmp_path / "fail"))
    record = json.loads(next((tmp_path / "fail").rglob("analysis_record.json")).read_text(encoding="utf-8"))
    assert record["status"] == "failed" and record["error"]


def test_cancel_preserves_completed_run(source, result, tmp_path):
    before = (result["directory"] / "analysis_record.json").read_bytes()
    with pytest.raises(Cancelled):
        analyze_request(AnalysisRequest(source, "cancelled", output=tmp_path / "cancel"), cancelled=lambda: True)
    record = json.loads(next((tmp_path / "cancel").rglob("analysis_record.json")).read_text(encoding="utf-8"))
    assert record["status"] == "cancelled"
    assert (result["directory"] / "analysis_record.json").read_bytes() == before


@pytest.mark.parametrize("extension", ["png", "tiff", "pdf", "svg"])
def test_export_formats(tmp_path, result, extension):
    path = tmp_path / f"export.{extension}"
    export_figure(result, "RL_2D", path, lambda *args: None, lambda: False, dpi=30)
    assert path.stat().st_size > 100


def test_export_cannot_overwrite_provenance(result):
    with pytest.raises(ValueError, match="追溯"):
        export_figure(result, "RL_2D", result["directory"] / "figures" / "RL_2D.png", lambda *args: None, lambda: False)


def test_open_output_uses_completed_directory(window, result, monkeypatch):
    urls = []
    monkeypatch.setattr("gui.pages.single_sample_page.QDesktopServices.openUrl", lambda url: urls.append(url) or True)
    window.single.completed = result
    window.single.parameters.output.setText("not-the-run")
    window.single.open_output()
    assert Path(urls[0].toLocalFile()) == result["directory"].resolve()


def test_xlsx_import(source, frame, tmp_path):
    path = tmp_path / "synthetic.xlsx"
    frame.to_excel(path, index=False)
    info = inspect_file(path, {"imaginary_convention": "loss"})
    assert info["points"] == 3 and info["status"] == "PENDING"


def test_folder_import_isolates_failures(window, source, tmp_path, qtbot):
    (tmp_path / "bad.csv").write_text("bad\n1\n")
    window.single.import_paths([tmp_path])
    qtbot.waitUntil(lambda: not window.single.busy)
    assert len(window.single.table.sources) == 2
    statuses = [item.data(0, Qt.ItemDataRole.UserRole)["status"] for item in window.single.table.sources.values()]
    assert set(statuses) == {"PENDING", "FAIL"}


def test_xls_real_binary_parser(frame):
    from core.parser import read_sample
    path = Path(__file__).resolve().parents[1] / "sample_data/synthetic_legacy.xls"
    data = read_sample(path, imaginary_convention="loss")
    pd.testing.assert_frame_equal(data.data, frame)


def test_drag_drop_uses_import(window, source, monkeypatch):
    from PySide6.QtCore import QPoint, QPointF
    calls = []
    monkeypatch.setattr(window.single, "import_paths", lambda paths: calls.append(paths))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(source))])
    enter = QDragEnterEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dragEnterEvent(enter)
    assert enter.isAccepted()
    event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dropEvent(event)
    assert len(calls) == 1 and [Path(p) for p in calls[0]] == [source]
    assert window.stack.currentWidget() is window.single


def test_cancel_button_and_close_guard(window, qtbot):
    import threading
    started = threading.Event()
    release = threading.Event()
    def operation(progress, cancelled):
        started.set()
        release.wait(2)
        if cancelled():
            raise Cancelled("已取消")
    window.single._launch(operation, lambda result: None)
    qtbot.waitUntil(started.is_set)
    assert not window.single.files.isEnabled()
    assert window.close() is False
    assert window.single.worker.isInterruptionRequested()
    release.set()
    qtbot.waitUntil(lambda: not window.single.busy)
    assert window.single.files.isEnabled()
    assert "已取消" in window.single.error.text()


def test_cancel_after_data_saved(source, tmp_path):
    requested = False
    def progress(percent, text):
        nonlocal requested
        if percent == 50:
            requested = True
    with pytest.raises(Cancelled):
        analyze_request(AnalysisRequest(source, "cancel_after_write", output=tmp_path / "partial", dpi=30),
                        progress, lambda: requested)
    record_path = next((tmp_path / "partial").rglob("analysis_record.json"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "cancelled"
    assert (record_path.parent / "RL_matrix.csv").exists()
    assert record["artifacts_sha256"]["RL_matrix.csv"]


def test_frequency_crop_uses_only_original_points(source, tmp_path):
    request = AnalysisRequest(source, "crop", output=tmp_path, frequency_min=2.1, frequency_max=4,
                              thickness_min=1, thickness_max=1, dpi=30)
    result = analyze_request(request)
    np.testing.assert_array_equal(result["result"].frequency_ghz, [3., 4.])
    assert result["record"]["selected_source_rows"] == [3, 4]


def test_nonstandard_threshold_keeps_standard_eab(source, tmp_path):
    result = analyze_request(AnalysisRequest(source, "threshold", output=tmp_path, threshold=-5,
                                             thickness_min=1, thickness_max=1, dpi=30))
    assert result["summary"]["standard_eab"]["threshold_db"] == -10
    assert "EAB" not in result["summary"]["selected_threshold_bandwidth"]["metric"]


def test_empty_dialog_keeps_state(qtbot, monkeypatch):
    selector = FileSelector()
    qtbot.addWidget(selector)
    monkeypatch.setattr("gui.widgets.file_selector.QFileDialog.getOpenFileNames", lambda *args: ([], ""))
    seen = []
    selector.files_selected.connect(seen.append)
    selector.choose_files()
    assert seen == []


def test_toolbar_save_cannot_bypass_export():
    from gui.widgets.plot_canvas import ScientificToolbar
    assert all(item[0] != "Save" for item in ScientificToolbar.toolitems)


def test_switching_source_restores_completed_snapshot(qtbot, source, tmp_path, result):
    """分析 A 后切到未分析的 B 再切回 A：直接还原 A 的原快照，不重新计算。"""
    page = SingleSamplePage()
    qtbot.addWidget(page)
    info = inspect_file(source, {"imaginary_convention": "loss"})
    other = dict(info, path=tmp_path / "second.csv", sample="second")
    page.select_source(info)
    page._analyzed(result)
    page._set_busy(False)
    assert page.completed is result
    page.select_source(other)
    assert page.completed is None
    assert "尚未生成单样品分析结果" in page.summary.toPlainText()
    assert page.plot.selector.count() == 0 and page.plot.current_figure() is None
    page.select_source(info)
    assert page.completed is result
    assert page.completed["directory"] == result["directory"]
    assert "Maximum EAB" in page.summary.toPlainText()
    assert page.plot.selector.count() == len(result["figures"])
    assert page.start_button.isEnabled()
    assert page.open_button.isEnabled()


def test_restoring_snapshot_does_not_recompute_or_reemit(qtbot, source, tmp_path, result):
    """切回来只读缓存：不启动后台任务，也不再次广播完成信号。"""
    page = SingleSamplePage()
    qtbot.addWidget(page)
    info = inspect_file(source, {"imaginary_convention": "loss"})
    events = []
    page.analysis_completed.connect(events.append)
    page.select_source(info)
    page._analyzed(result)
    page._set_busy(False)
    page.select_source(dict(info, path=tmp_path / "other.csv"))
    page.select_source(info)
    assert events == [result]
    assert page.worker is None
    assert page.snapshots[page._snapshot_key(source)]["result"] is result


def test_snapshot_keeps_explored_thickness_when_switching(qtbot, source, tmp_path, result):
    """滑块探索状态随快照保存；切到别的文件再切回来仍指向同一快照。"""
    from types import SimpleNamespace

    page = SingleSamplePage()
    qtbot.addWidget(page)
    info = inspect_file(source, {"imaginary_convention": "loss"})
    page.select_source(info)
    page._analyzed(result)
    page._set_busy(False)
    explored = {"curve": SimpleNamespace(thickness_mm=[1.0])}
    page.explored = explored
    page._sync_view()
    page.select_source(dict(info, path=tmp_path / "other.csv"))
    assert page.explored is None
    page.select_source(info)
    assert page.explored is explored

