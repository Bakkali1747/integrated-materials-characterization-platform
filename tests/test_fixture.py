from pathlib import Path

from core.fixture import find_fixture_for_sample, read_fixture
from gui.controllers.analysis_controller import AnalysisRequest, filename_hints, inspect_file, request_with_fixture_thickness
from gui.controllers.comparison_controller import compare_requests
from gui.main_window import MainWindow

SDAT_HEADER = """<Cluster>
<Name></Name>
<NumElts>2</NumElts>
<Cluster>
<Name>夹具</Name>
<NumElts>5</NumElts>
<EW>
<Name>类型</Name>
<Choice>同轴空气线</Choice>
<Val>0</Val>
</EW>
<DBL><Name>L</Name><Val>20.0</Val></DBL>
<DBL><Name>A</Name><Val>0.0</Val></DBL>
<DBL><Name>B</Name><Val>17.88</Val></DBL>
<DBL><Name>D</Name><Val>2.12</Val></DBL>
</Cluster>
<Cluster>
<Name>环境</Name>
<NumElts>1</NumElts>
<DBL><Name>温度</Name><Val>25.0</Val></DBL>
</Cluster>
</Cluster>
"""


def make_files(tmp_path):
    memp = tmp_path / "0.2_2_18_401_25_20261020141657.memp"
    memp.write_text(
        "样品名称：0.2\n测试类型：同轴传输线法\n测试频率：2~18GHz,2\n\n"
        "频率(GHz)\t介电实部\t介电虚部\t磁导实部\t磁导虚部\n"
        "2.000000\t10.432324\t1.919965\t1.749214\t0.642450\n"
        "18.000000\t8.000000\t1.000000\t1.200000\t0.300000\n", encoding="gbk")
    sdat = tmp_path / "0.2_S-parameter_2_18_25_20261020141657.sdat"
    sdat.write_text(SDAT_HEADER + "2.000000\t-0.19\t-0.25\n18.000000\t-0.5\t0.1\n", encoding="gbk")
    return memp, sdat


def test_pairs_when_only_sample_name_remains(tmp_path):
    memp, sdat = make_files(tmp_path)
    simple_memp = memp.with_name("0.2.memp")
    simple_sdat = sdat.with_name("0.2.sdat")
    memp.rename(simple_memp)
    sdat.rename(simple_sdat)
    assert find_fixture_for_sample(simple_memp)["thickness_mm"] == 2.12


def test_does_not_pair_neighbouring_sample_id(tmp_path):
    memp, sdat = make_files(tmp_path)
    sdat.unlink()
    other = tmp_path / "0.25.sdat"
    other.write_text(SDAT_HEADER.replace("2.12", "9.99"), encoding="gbk")
    assert find_fixture_for_sample(memp) == {}


def test_read_fixture_and_sibling(tmp_path):
    memp, sdat = make_files(tmp_path)
    fixture = read_fixture(sdat)
    assert fixture["thickness_mm"] == 2.12
    assert fixture["temperature_c"] == 25
    assert fixture["fixture_type"] == "同轴空气线"
    assert fixture["source_sha256"]
    paired = find_fixture_for_sample(memp)
    assert paired["thickness_mm"] == 2.12
    assert Path(paired["source"]).resolve() == sdat.resolve()


def test_filename_hints_do_not_treat_sample_id_as_thickness(tmp_path):
    memp, _ = make_files(tmp_path)
    hints = filename_hints(memp)
    assert hints == {"sample_id": "0.2", "frequency_min_ghz": 2.0,
                     "frequency_max_ghz": 18.0, "points": 401, "temperature_c": 25}
    assert "thickness_mm" not in hints


def test_batch_request_uses_fixture_thickness(tmp_path):
    memp, _ = make_files(tmp_path)
    request = AnalysisRequest(path=memp, name="0.2", curve_thickness=2.0)
    adjusted = request_with_fixture_thickness(request)
    assert adjusted.curve_thickness == 2.12
    assert adjusted.source_hints["fixture"]["thickness_mm"] == 2.12


def test_comparison_accepts_memp_with_different_fixture_thickness(tmp_path):
    """两个 .memp 的 sdat 夹具厚度不同（2.12 / 3.50 mm）时仍可直接比较。"""
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    memp_a, _ = make_files(first)
    memp_b, sdat_b = make_files(second)
    sdat_b.write_text(SDAT_HEADER.replace("<Val>2.12</Val>", "<Val>3.50</Val>")
                      + "2.000000\t-0.19\t-0.25\n18.000000\t-0.5\t0.1\n", encoding="gbk")
    shared = dict(output=tmp_path / "out", thickness_max=1.1, thickness_step=.1, dpi=25)
    request_a = request_with_fixture_thickness(AnalysisRequest(memp_a, "A", **shared))
    request_b = request_with_fixture_thickness(AnalysisRequest(memp_b, "B", **shared))
    assert (request_a.curve_thickness, request_b.curve_thickness) == (2.12, 3.5)
    result = compare_requests([request_a, request_b], tmp_path / "out", lambda *args: None, lambda: False, dpi=25)
    comparison = result["record"]["comparison"]
    assert result["record"]["success_count"] == 2
    assert comparison["identical_curve_thickness"] is False
    assert comparison["curve_thickness_mm_per_sample"] == {"A": 2.12, "B": 3.5}
    assert result["curve_thicknesses"] == {"A": 2.12, "B": 3.5}


def test_single_page_autofills_fixture_thickness(qtbot, tmp_path):
    memp, _ = make_files(tmp_path)
    info = inspect_file(memp, {"imaginary_convention": "loss"})
    assert info["sample"] == "0.2"
    window = MainWindow()
    qtbot.addWidget(window)
    window.single.select_source(info)
    assert window.single.parameters.fields["curve_thickness"].value() == 2.12
    assert "D=2.12 mm" in window.single.hint.text()
    assert not window.single.hint.isHidden()


def test_daily_mode_hides_and_restores_advanced_pages(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_ui_mode("simple")
    assert window.ui_mode == "simple"
    assert window.navigation.isRowHidden(3)
    assert window.navigation.isRowHidden(4)
    assert window.navigation.isRowHidden(5)
    assert window.single.reference_button.isHidden()
    window.set_ui_mode("full")
    assert not window.navigation.isRowHidden(3)
    assert not window.single.reference_button.isHidden()
