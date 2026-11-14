"""类型化导航与 VSM/XRD/S 参数比较/批量的基础测试。"""

import pandas as pd

from gui.controllers.quality_controller import quality_rows
from gui.main_window import MainWindow
from gui.pages.typed_batch_pages import VsmBatchPage
from gui.pages.typed_comparison_pages import _s_row, _vsm_row, _xrd_row


def test_type_navigation_has_compare_and_batch_children(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    for prefix in ("em", "vsm", "xrd", "sparameter"):
        for suffix in ("single", "compare", "batch"):
            assert f"{prefix}.{suffix}" in window.navigation.leaves
    assert window.navigation.leaves["vsm.compare"].parent().text(0).lstrip("▸▼ ") == "VSM 分析"
    assert window.navigation.leaves["xrd.batch"].parent().text(0).lstrip("▸▼ ") == "XRD 分析"

    window.show_page("xrd.compare")
    assert window.stack.currentWidget() is window.xrd_comparison
    window.show_page("sparameter.batch")
    assert window.stack.currentWidget() is window.sparameter_batch


def test_daily_mode_hides_only_advanced_type_entries(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_ui_mode("simple")
    assert window.navigation.is_page_visible("em.single")
    assert window.navigation.is_page_visible("vsm.single")
    assert window.navigation.is_page_visible("xrd.single")
    assert not window.navigation.is_page_visible("em.compare")
    assert not window.navigation.is_page_visible("vsm.batch")
    assert not window.navigation.is_page_visible("sparameter.single")
    window.set_ui_mode("full")
    assert window.navigation.is_page_visible("sparameter.compare")
    assert window.navigation.is_page_visible("vsm.batch")


def test_groups_collapsed_until_selected(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert not any(group.isExpanded() for group in window.navigation.groups.values())
    window.show_page("xrd.compare")
    assert window.navigation.groups["xrd"].isExpanded()
    assert not window.navigation.groups["vsm"].isExpanded()
    vsm = window.navigation.groups["vsm"]
    window.navigation._toggle_group(vsm, 0)
    assert vsm.isExpanded()
    window.navigation._toggle_group(vsm, 0)
    assert not vsm.isExpanded()


def test_comparison_rows_for_each_type():
    vsm = {"record": {"sample": "v", "status": "success", "validation_status": "pending"},
           "metrics": {"Hc_oe": 10.0, "Mr": 1.0, "Ms": 2.0, "squareness": .5}}
    assert _vsm_row(vsm)[:5] == ["v", 10.0, 1.0, 2.0, .5]

    xrd = {"record": {"sample": "x", "status": "success", "validation_status": "pending"},
           "metrics": {"peaks": [{"center_deg": 20.0, "d_angstrom": 2.5, "fwhm_deg": .2,
                                  "crystallite_size_nm": 10.0, "relative_intensity_pct": 100.0}]}}
    assert _xrd_row(xrd)[:6] == ["x", 1, 20.0, 2.5, .2, 10.0]

    sparameter = {"record": {"sample": "s", "status": "success",
                             "schema_status": "candidate_high_confidence"},
                  "table": pd.DataFrame({"S11_db": [-10.0, -20.0], "S21_db": [-1.0, -3.0]})}
    assert _s_row(sparameter)[:4] == ["s", -20.0, -3.0, "candidate_high_confidence"]


def test_vsm_batch_scan_filters_supported_files(qtbot, tmp_path):
    (tmp_path / "a.csv").write_text("x", encoding="utf-8")
    (tmp_path / "b.dat").write_text("x", encoding="utf-8")
    (tmp_path / "c.raw").write_text("x", encoding="utf-8")
    page = VsmBatchPage()
    qtbot.addWidget(page)
    page.folder.setText(str(tmp_path))
    page.scan()
    assert [path.name for path in page.files] == ["a.csv", "b.dat"]


def test_history_quality_is_type_aware():
    rows = quality_rows({"analysis_kind": "vsm_hysteresis", "status": "success",
                         "validation_status": "pending_external_vsm_reference"})
    assert ("Analysis kind", "PASS", "vsm_hysteresis") in rows
    assert not any("Frequency monotonic" in row[0] for row in rows)
