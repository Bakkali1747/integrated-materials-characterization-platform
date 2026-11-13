"""GUI Phase 2 适配与交互，不重写科学数值测试。"""
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import Qt

from gui.controllers.analysis_controller import AnalysisRequest, Cancelled, analyze_request
from gui.controllers.comparison_controller import compare_requests
from gui.controllers.export_controller import export_figure
from gui.controllers.science_figures import make_figure
from gui.controllers.sparameter_controller import analyze_s_request, s_figure
from gui.pages.comparison_page import ComparisonPage
from gui.pages.sparameter_page import SParameterPage
from gui.widgets.metrics_table import MetricsTable
from plotting.style import PlotStyle, plt
from plotting.theory_measured import CAUTION, plot_theory_measured


@pytest.fixture(scope="module")
def scientific(tmp_path_factory):
    root = tmp_path_factory.mktemp("science")
    path = root / "synthetic.csv"
    pd.DataFrame({"frequency_ghz": [2., 3., 4.], "eps_real": [4., 4.1, 4.2], "eps_imag": [.2, .3, .4],
                  "mu_real": [1.5, 1.4, 1.3], "mu_imag": [.3, .4, .5]}).to_csv(path, index=False)
    request = AnalysisRequest(path, "synthetic", output=root, thickness_max=1.1, thickness_step=.1, full_science=True, dpi=25)
    return analyze_request(request)


@pytest.fixture(scope="module")
def sresult(tmp_path_factory):
    root = tmp_path_factory.mktemp("sdata")
    path = root / "synthetic.sdat"
    lines = ['<Cluster><Name>合成测试</Name></Cluster>']
    for i in range(201):
        values = [2+i*.08, .8 if i == 0 else .1, 0, .8, 0, .8, 0, .1, 0]
        lines.append("\t".join(str(v) for v in values))
    path.write_bytes("\n".join(lines).encode("gb18030"))
    return analyze_s_request(path, "synthetic", root, "", lambda *a: None, lambda: False, dpi=25)


@pytest.fixture(scope="module")
def comparison(tmp_path_factory, scientific):
    root = tmp_path_factory.mktemp("compare")
    path = Path(scientific["record"]["raw_file"])
    base = AnalysisRequest(path, "one", output=root, thickness_max=1.1, thickness_step=.1)
    return compare_requests([base, replace(base, name="two")], root, lambda *a: None, lambda: False, dpi=25)


def test_full_science_has_all_views(scientific):
    assert len(scientific["figures"]) == 17
    assert {"RL_3D", "tan_delta_eps", "tan_delta_mu", "impedance", "attenuation", "Cole_Cole", "C0", "quarter_wave"} <= set(scientific["figures"])
    assert scientific["record"]["phase2"]["units"]["alpha_per_m"] == "m^-1"


def test_full_science_matches_cli(scientific, tmp_path):
    from run_analysis import analyze
    root = analyze(scientific["record"]["raw_file"], output=tmp_path, imaginary_convention="loss", thickness_max=1.1, thickness_step=.1, style=PlotStyle(dpi=25))
    for name in ("RL_matrix.csv", "loss_parameters.csv", "impedance_real_matrix.csv"):
        np.testing.assert_allclose(pd.read_csv(root/name).to_numpy(), pd.read_csv(scientific["directory"]/name).to_numpy(), rtol=0, atol=0)


@pytest.mark.parametrize("key", ["RL_3D", "tan_delta_eps", "impedance", "attenuation", "Cole_Cole", "C0", "quarter_wave"])
def test_science_export_registry(scientific, key, tmp_path):
    path = tmp_path / f"{key}.svg"
    export_figure(scientific, key, path, lambda *a: None, lambda: False, dpi=25)
    assert path.stat().st_size > 100


def test_single_tangent_selects_existing_column(scientific):
    fig = make_figure(scientific, "tan_delta_mu", PlotStyle(dpi=25))
    np.testing.assert_allclose(fig.axes[0].lines[0].get_ydata(), scientific["science_table"].tan_delta_mu)
    assert len(fig.axes[0].lines) == 1
    plt.close(fig)


def test_s_candidate_and_negative_a_preserved(sresult):
    assert sresult["record"]["schema_status"] == "candidate_high_confidence"
    assert sresult["record"]["quality_checks"]["negative_absorption_count"] == 1
    assert sresult["table"].A.iloc[0] == pytest.approx(-.28)
    assert len(sresult["table"]) == 201
    assert sresult["record"]["clipping"] == "OFF"
    assert {"SE_R_db", "SE_A_db", "SE_T_db"} <= set(sresult["table"].columns)


@pytest.mark.parametrize("quantity,lines", [("magnitude",1), ("db",1), ("real_imag",2), ("phase_deg",1),
                                            ("RTA",3), ("SE",3), ("smith",4)])
def test_s_quantity_selection(sresult, quantity, lines):
    fig = s_figure(sresult, quantity, "S21", dpi=25)
    assert len(fig.axes[0].lines) == lines
    assert "manufacturer-confirmed" in fig._suptitle.get_text()
    assert fig.axes[0].get_ylabel() != "RL (dB)"


def test_s_page_warning_and_point_table(qtbot, sresult):
    page = SParameterPage(); qtbot.addWidget(page)
    page.analyzed(sresult)
    assert page.badge.status == "candidate_high_confidence"
    assert "WARNING" in page.error.text()
    assert page.points.rowCount() == 201


def test_theory_measured_keeps_independent_grids(scientific, sresult):
    fig = plot_theory_measured(scientific["curve"], sresult["table"])
    assert [len(line.get_xdata()) for line in fig.axes[0].lines] == [3, 201]
    assert "Calculated RL" in fig.axes[0].lines[0].get_label()
    assert fig.axes[0].lines[1].get_label() == "Measured S11"
    assert "different measurement conditions" in CAUTION
    plt.close(fig)


def test_comparison_has_ten_metrics_and_exports(comparison):
    assert len(comparison["figures"]) == 10
    assert (comparison["directory"] / "summary.xlsx").exists()
    assert comparison["record"]["success_count"] == 2
    assert {r["sample"] for r in comparison["minima"]} == {"one", "two"}


def test_comparison_hashes(comparison):
    for path, digest in comparison["record"]["artifacts_sha256"].items():
        assert hashlib.sha256((comparison["directory"] / path).read_bytes()).hexdigest() == digest


def test_table_all_ties_highlight_and_numeric_sort(qtbot, comparison):
    table = MetricsTable(); qtbot.addWidget(table)
    table.load_rows(comparison["summaries"], True)
    assert table.item(0,2).background().color().name() == "#e5eef8"
    assert table.item(1,2).background().color().name() == "#e5eef8"
    table.load_rows([{"sample":"a","rl_min_db":-2.,"status":"success"}, {"sample":"b","rl_min_db":-10.,"status":"success"}], False)
    table.sortItems(2, Qt.SortOrder.AscendingOrder)
    assert table.item(0,0).text() == "b"
    assert table.item(0,2).background().style() == Qt.BrushStyle.NoBrush


def test_check_selection_controls(qtbot, scientific):
    page = ComparisonPage(); qtbot.addWidget(page)
    page.add_source(scientific["record"]["raw_file"], "one")
    page.check_all(False); assert page.selected_requests() == []
    page.invert(); assert len(page.selected_requests()) == 1
    page.check_all(True); assert page.selected_requests()[0].name == "one"


def test_mixed_curve_thickness_is_comparable(scientific, tmp_path):
    """不同厚度的样品同样可比：各自保留自身厚度，并在记录与图标题中标注。"""
    base = AnalysisRequest(Path(scientific["record"]["raw_file"]), "one", thickness_max=1.1, thickness_step=.1, dpi=25)
    result = compare_requests([base, replace(base, name="two", curve_thickness=3)], tmp_path,
                              lambda *a: None, lambda: False, dpi=25)
    comparison = result["record"]["comparison"]
    assert comparison["identical_curve_thickness"] is False
    assert comparison["curve_thickness_mm"] is None
    assert comparison["curve_thickness_mm_per_sample"] == {"one": 2.0, "two": 3.0}
    assert any("厚度不同" in note for note in comparison["notes"])
    assert result["curve_thicknesses"] == {"one": 2.0, "two": 3.0}
    assert (result["directory"] / "figures" / "rl_db.png").is_file()
    assert result["record"]["success_count"] == 2


def test_uniform_curve_thickness_records_common_value(comparison):
    record = comparison["record"]["comparison"]
    assert record["identical_curve_thickness"] is True
    assert record["curve_thickness_mm"] == 2
    assert set(record["curve_thickness_mm_per_sample"].values()) == {2}


def test_thickness_caption_for_common_and_per_sample():
    from plotting.comparison_plot import thickness_caption
    assert thickness_caption(2) == "Common thickness: 2 mm"
    assert thickness_caption({"a": 2, "b": 2}) == "Common thickness: 2 mm"
    caption = thickness_caption({"a": 2, "b": 3})
    assert caption.startswith("Thickness per sample:") and "a 2 mm" in caption and "b 3 mm" in caption


def test_different_grid_preserved(scientific, tmp_path):
    from run_batch import compare_runs
    # 使用两个正式运行，第二个显式裁选已有点。
    request = AnalysisRequest(Path(scientific["record"]["raw_file"]), "subset", output=tmp_path, thickness_max=1.1, thickness_step=.1,
                              frequency_min=3, full_science=True, dpi=25)
    result = analyze_request(request)
    record = compare_runs([("full", scientific["directory"]), ("subset", result["directory"])], tmp_path/"comparison", PlotStyle(dpi=25), 2)
    assert record["identical_frequency_grids"] is False
    table = pd.read_csv(tmp_path/"comparison/eps_real.csv")
    assert table.groupby("sample").size().to_dict() == {"full":3, "subset":2}


def test_cross_page_worker_lock(qtbot):
    import threading

    from gui.main_window import MainWindow
    window = MainWindow(); qtbot.addWidget(window)
    release = threading.Event()
    window.sparameters.launch(lambda *a: release.wait(2), lambda value: None)
    assert not window.single.isEnabled() and not window.comparison.isEnabled()
    release.set()
    qtbot.waitUntil(lambda: not window.sparameters.busy)
    assert window.single.isEnabled() and window.comparison.isEnabled()


def test_comparison_cancellation_is_recorded(scientific, tmp_path):
    request = AnalysisRequest(Path(scientific["record"]["raw_file"]), "one")
    with pytest.raises(Cancelled):
        compare_requests([request], tmp_path, lambda *a: None, lambda: True)
    record = json.loads(next(tmp_path.rglob("batch_record.json")).read_text(encoding="utf-8"))
    assert record["status"] == "cancelled"


def test_theory_comparison_records_both_sources(scientific, sresult):
    from gui.controllers.sparameter_controller import theory_comparison
    before = (sresult["directory"] / "analysis_record.json").read_bytes()
    fig, directory = theory_comparison(scientific, sresult, lambda *a: None, lambda: False, dpi=25)
    record = json.loads((directory / "comparison_record.json").read_text(encoding="utf-8"))
    assert record["theory_raw_sha256"] == scientific["record"]["raw_sha256"]
    assert record["measured_raw_sha256"] == sresult["record"]["raw_sha256"]
    assert record["conditions_equivalence"] == "unconfirmed"
    assert (sresult["directory"] / "analysis_record.json").read_bytes() == before


def test_comparison_failure_isolation(scientific, tmp_path):
    path = Path(scientific["record"]["raw_file"])
    request = AnalysisRequest(path, "good", thickness_max=1.1, thickness_step=.1)
    result = compare_requests([request, replace(request, path=tmp_path/"missing.csv", name="bad")], tmp_path,
                              lambda *a: None, lambda: False, dpi=25)
    assert result["record"]["status"] == "partial_failure"
    assert result["record"]["failure_count"] == 1
    assert result["summaries"][1].get("rl_min_db") is None


def test_s_custom_schema_status_preserved(sresult, tmp_path):
    from core.sparameter_mapping import SParameterMapping
    config = SParameterMapping(schema_status="unverified").to_dict()
    schema = tmp_path / "schema.json"; schema.write_text(json.dumps(config))
    result = analyze_s_request(sresult["record"]["raw_file"], "custom", tmp_path, str(schema), lambda *a: None, lambda: False, dpi=25)
    assert result["record"]["schema_status"] == "unverified"
    assert result["record"]["schema_file_sha256"] == hashlib.sha256(schema.read_bytes()).hexdigest()


def test_comparison_plot_retains_viewing_space(qtbot):
    from gui.main_window import MainWindow
    window = MainWindow(); qtbot.addWidget(window)
    window.show(); window.navigation.setCurrentRow(5)
    qtbot.wait(30)
    assert window.comparison.plot.height() > 300
    assert window.comparison.tabs.count() == 3


def test_changed_comparison_data_cannot_be_exported(qtbot, comparison, monkeypatch):
    page = ComparisonPage(); qtbot.addWidget(page)
    page.analyzed(comparison)
    metric = page.plot.selector.currentData()
    path = comparison["directory"] / "figures" / f"{metric}.csv"
    original = path.read_bytes()
    monkeypatch.setattr(page, "save_plot", lambda builder: builder())
    try:
        path.write_bytes(original + b"\n")
        with pytest.raises(ValueError, match="已改变"):
            page.save_selected()
    finally:
        path.write_bytes(original)
