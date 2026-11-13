"""VSM 解析、单位、磁滞指标、背景扣除、运行产物与报告。"""

import math

import numpy as np
import pytest

from core.vsm import analyze_vsm, inspect_vsm_table, read_vsm, suggest_vsm_columns
from core.vsm_service import VSMConfig, execute, load_completed_vsm_run
from export.vsm_report import export_vsm_report


def loop_rows(*, hc=100.0, ms=20.0, width=120.0, hmax=3000.0, step=60.0, mass_g=0.01,
              slope=0.0, intercept=0.0):
    """返回 (H Oe, moment emu) 的完整往返数据；Hc 已知，Mr 由 tanh 决定。"""
    up = np.arange(-hmax, hmax + step / 2, step)
    down = np.arange(hmax - step, -hmax - step / 2, -step)
    field = np.concatenate([up, down])
    values = np.concatenate([ms * np.tanh((up - hc) / width), ms * np.tanh((down + hc) / width)])
    moment = values * mass_g + slope * field + intercept
    return field, moment


def write_loop(path, **values):
    field, moment = loop_rows(**values)
    path.write_text("field_oe,moment_emu\n" + "\n".join(f"{h},{m}" for h, m in zip(field, moment)),
                    encoding="utf-8")
    return path


def write_dat(path, *, mass_g=0.01, hc=100.0, ms=20.0, width=120.0, hmax=3000.0,
              step=60.0, unit="CGS"):
    """构造 Lake Shore 风格 DAT（GBK），结构与本项目已观察的真实文件一致。"""
    up = np.arange(-hmax, hmax + step / 2, step)
    down = np.arange(hmax, -hmax - step / 2, -step)
    field = np.concatenate([down, up[1:]])
    values = np.concatenate([ms * np.tanh((down + hc) / width), ms * np.tanh((up[1:] - hc) / width)])
    moment = values * mass_g
    header = (f"ID=测试样品  Mass(g)={mass_g}  Volume(cm^3)=0  Area(mm^2)=0  slope=0  constant=0  "
              f"Unit={unit}  Rate(A/s)=0.500  Room_T(℃)=22.0  PoleGap=Gap2  emuFactor(emu/V)=2.0")
    metrics = f"Hci(Oe)={hc}  Hci1(Oe)=-{hc}  Hci2(Oe)={hc}  Mr(emu)=0.1  Mr1(emu)=0.1  Mr2(emu)=-0.1  Ms(emu)={ms * mass_g}"
    columns = ("Time(s)\tField(Oe)\tTemperature(K)\tAngle(deg)\tMoment(emu)\t"
               "Magnetization(Mass)(emu/g)\tLockX(V)\tLcokY(V)\tInduction(Gs)")
    rows = ["\t".join(["12:00:00.000", f"{h:.6E}", "NaN", "NaN", f"{m:.6E}",
                       f"{m / mass_g:.6E}", "0", "0", "Inf"]) for h, m in zip(field, moment)]
    path.write_bytes("\n".join([header, metrics, columns, *rows]).encode("gbk"))
    return path


def test_read_lakeshore_dat_auto_units_mass_and_metrics(tmp_path):
    source = write_dat(tmp_path / "sample.dat")

    data = read_vsm(source)

    assert data.name == "测试样品"
    assert data.metadata["parser"] == "lakeshore-dat-v1"
    assert data.metadata["mass_mg"] == pytest.approx(10.0)
    assert data.metadata["mass_source"] == "dat_header"
    assert data.metadata["field_unit"] == "Oe" and data.metadata["moment_unit"] == "emu"
    assert data.metadata["column_map"] == {"field": "Field(Oe)", "moment": "Moment(emu)"}
    assert data.metadata["instrument_metrics"]["Hci(Oe)"] == "100.0"
    assert data.frame["magnetization"].iloc[0] == pytest.approx(
        20 * math.tanh((3000 + 100) / 120), abs=.1)

    result = analyze_vsm(data)
    assert result["status"] == "success"
    assert result["metrics"]["Hc_oe"] == pytest.approx(100.0, abs=1.0)
    assert result["metrics"]["Mr"] == pytest.approx(20 * math.tanh(100 / 120), abs=.2)
    assert result["metrics"]["Ms"] == pytest.approx(20.0, abs=.2)


def test_read_lakeshore_dat_user_mass_overrides_header(tmp_path):
    source = write_dat(tmp_path / "sample.dat", mass_g=0.01)

    data = read_vsm(source, mass_mg=20.0)

    assert data.metadata["mass_mg"] == pytest.approx(20.0)
    assert data.metadata["mass_source"] == "user"
    assert any("相差超过" in warning for warning in data.warnings)


def test_read_lakeshore_dat_auto_filled_mass_keeps_header_source(tmp_path):
    source = write_dat(tmp_path / "sample.dat", mass_g=0.01)

    data = read_vsm(source, mass_mg=10.0, mass_from_header=True)

    assert data.metadata["mass_mg"] == pytest.approx(10.0)
    assert data.metadata["mass_source"] == "dat_header"
    assert data.warnings == []


def test_read_lakeshore_dat_rejects_non_cgs_unit(tmp_path):
    source = write_dat(tmp_path / "sample.dat", unit="SI")
    with pytest.raises(ValueError, match="CGS"):
        read_vsm(source)


def test_inspect_lakeshore_dat_exposes_columns_and_mass(tmp_path):
    source = write_dat(tmp_path / "sample.dat")
    preview = inspect_vsm_table(source)
    assert "Field(Oe)" in preview["columns"] and "Moment(emu)" in preview["columns"]
    assert preview["metadata"]["mass_mg"] == pytest.approx(10.0)
    assert preview["metadata"]["parser"] == "lakeshore-dat-v1"


def test_vsm_page_prefills_dat_units_and_mass(qtbot, tmp_path):
    from gui.pages.vsm_page import VsmPage

    source = write_dat(tmp_path / "sample.dat")
    page = VsmPage()
    qtbot.addWidget(page)
    page.file.setText(str(source))
    page.name.setText("DAT")
    page.load_columns()

    assert page.field_column.currentText() == "Field(Oe)"
    assert page.moment_column.currentText() == "Moment(emu)"
    assert page.field_unit.currentText() == "Oe"
    assert page.moment_unit.currentText() == "emu"
    assert float(page.mass.text()) == pytest.approx(10.0)


def test_vsm_page_dat_analysis_records_header_mass_source(qtbot, tmp_path):
    from gui.pages.vsm_page import VsmPage

    source = write_dat(tmp_path / "sample.dat")
    page = VsmPage()
    qtbot.addWidget(page)
    page.export_dpi = 60
    page.file.setText(str(source))
    page.name.setText("DAT")
    page.output.setText(str(tmp_path / "out"))
    page.load_columns()
    assert page.mass_from_header is True
    page.start_analysis()
    qtbot.waitUntil(lambda: not page.busy, timeout=60000)
    assert page.completed is not None, page.error.text()
    assert page.completed["record"]["source"]["mass_source"] == "dat_header"
    assert page.completed["record"]["mass_normalization"] is True


def test_read_vsm_units_mass_and_order_preserved(tmp_path):
    source = tmp_path / "loop.csv"
    source.write_text("Field (Oe),Moment (emu)\n-100,0.1\n0,0.2\n100,0.3\n", encoding="utf-8")

    data = read_vsm(source, field_unit="Oe", moment_unit="emu", mass_mg=10.0)

    assert list(data.frame["field_oe"]) == [-100.0, 0.0, 100.0]
    assert data.frame["field_am"].iloc[0] == pytest.approx(-100 * 1000 / (4 * math.pi))
    assert data.frame["magnetization"].iloc[0] == pytest.approx(10.0)   # emu/g
    assert data.metadata["mass_normalized"] is True


def test_read_vsm_explicit_columns_convert_a_per_m_and_a_m2(tmp_path):
    source = tmp_path / "explicit.csv"
    source.write_text("H (A/m),m (A m^2)\n795.7747,0.002\n1591.5494,0.004\n", encoding="utf-8")

    data = read_vsm(source, field_column="H (A/m)", moment_column="m (A m^2)",
                    field_unit="A/m", moment_unit="A m^2")

    assert data.frame["field_oe"].iloc[0] == pytest.approx(10.0, rel=1e-5)
    assert data.frame["moment_emu"].iloc[0] == pytest.approx(2.0)
    assert data.frame["magnetization"].isna().all()


def test_read_vsm_requires_explicit_units_and_mapping(tmp_path):
    source = tmp_path / "loop.csv"
    source.write_text("Field (Oe),Moment (emu)\n-1,0.1\n0,0.2\n1,0.3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="磁场单位"):
        read_vsm(source, field_unit=None, moment_unit="emu")
    with pytest.raises(ValueError, match="磁矩单位"):
        read_vsm(source, field_unit="Oe", moment_unit=None)
    with pytest.raises(ValueError, match="无法作为表头|找不到|未找到"):
        read_vsm(source, field_unit="Oe", moment_unit="emu", field_column="Missing")


def test_read_vsm_missing_value_stops(tmp_path):
    source = tmp_path / "loop.csv"
    source.write_text("field_oe,moment_emu\n-1,0.1\n0,\n1,0.3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="缺失值"):
        read_vsm(source, field_unit="Oe", moment_unit="emu")


def test_suggest_columns_is_unique_only():
    assert suggest_vsm_columns(["Field (Oe)", "Moment (emu)"]) == ("Field (Oe)", "Moment (emu)")
    assert suggest_vsm_columns(["h", "field", "m"]) == (None, "m")


def test_analyze_hysteresis_metrics_on_known_loop(tmp_path):
    source = write_loop(tmp_path / "loop.csv")
    data = read_vsm(source, field_unit="Oe", moment_unit="emu", mass_mg=10.0)

    result = analyze_vsm(data)

    metrics = result["metrics"]
    assert result["status"] == "success"
    assert metrics["metrics_unit"] == "emu/g"
    assert metrics["Hc_oe"] == pytest.approx(100.0, abs=1.0)
    assert metrics["Hc_am"] == pytest.approx(metrics["Hc_oe"] * 1000 / (4 * math.pi), rel=1e-9)
    assert metrics["Mr"] == pytest.approx(20 * math.tanh(100 / 120), abs=.2)
    assert metrics["Ms"] == pytest.approx(20.0, abs=.2)
    assert metrics["squareness"] == pytest.approx(metrics["Mr"] / metrics["Ms"])
    assert result["quality"]["branch_count"] == 2
    assert result["quality"]["sorting"] == "preserved"
    assert result["quality"]["point_count"] == len(data.frame)


def test_analyze_background_correction_keeps_metrics(tmp_path):
    source = write_loop(tmp_path / "loop.csv", slope=.0005, intercept=.001)
    data = read_vsm(source, field_unit="Oe", moment_unit="emu", mass_mg=10.0)

    result = analyze_vsm(data, background_mode="linear_high_field", background_min_field_oe=2000)

    background = result["background"]
    assert background["mode"] == "linear_high_field"
    assert background["point_count"] >= 10
    assert background["r_squared"] > .99
    assert background["slope_emu_per_oe"] == pytest.approx(.0005, rel=.05)
    assert result["metrics"]["Hc_oe"] == pytest.approx(100.0, abs=2.0)
    assert result["metrics"]["Mr"] == pytest.approx(20 * math.tanh(100 / 120), abs=2.0)


def test_single_branch_is_flagged_but_metrics_reported(tmp_path):
    field, moment = loop_rows()
    source = tmp_path / "branch.csv"
    half = len(field) // 2
    source.write_text("field_oe,moment_emu\n" + "\n".join(
        f"{h},{m}" for h, m in zip(field[:half + 1], moment[:half + 1])), encoding="utf-8")
    data = read_vsm(source, field_unit="Oe", moment_unit="emu", mass_mg=10.0)

    result = analyze_vsm(data)

    assert any("一个" in warning for warning in result["warnings"])
    assert result["quality"]["branch_count"] == 1


def test_no_zero_crossing_is_not_computable(tmp_path):
    source = tmp_path / "positive.csv"
    source.write_text("field_oe,moment_emu\n" + "\n".join(
        f"{h},{0.2 + 0.0001 * h}" for h in range(100, 3100, 100)), encoding="utf-8")
    data = read_vsm(source, field_unit="Oe", moment_unit="emu", mass_mg=10.0)

    result = analyze_vsm(data)

    assert result["status"] == "not_computable"
    assert result["metrics"]["Hc_oe"] is None
    assert result["metrics"]["Mr"] is None
    assert any("Hc 不可计算" in warning or "零场" in warning for warning in result["warnings"])


def test_execute_writes_run_and_reloads(tmp_path):
    source = write_loop(tmp_path / "loop.csv")
    config = VSMConfig(path=source, name="synthetic", output=tmp_path / "out", mass_mg=10.0, dpi=40)
    result = execute(config)

    assert result.record["status"] == "success"
    assert result.record["analysis_kind"] == "vsm_hysteresis"
    assert (result.directory / "parsed_data.csv").is_file()
    assert (result.directory / "vsm_metrics.json").is_file()
    assert (result.directory / "vsm_metrics.csv").is_file()
    assert (result.directory / "analysis_record.txt").is_file()
    saved = load_completed_vsm_run(result.directory)
    assert saved["metrics"]["Hc_oe"] == pytest.approx(result.analysis["metrics"]["Hc_oe"])
    assert len(saved["table"]) == len(result.table)


def test_execute_invalid_configuration_creates_no_run(tmp_path):
    source = write_loop(tmp_path / "loop.csv")
    config = VSMConfig(path=source, name="synthetic", output=tmp_path / "out", mass_mg=-1.0)
    with pytest.raises(ValueError, match="质量"):
        execute(config)
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").rglob("analysis_record.json"))


def test_export_vsm_report_from_completed_run(tmp_path):
    source = write_loop(tmp_path / "loop.csv")
    result = execute(VSMConfig(path=source, name="synthetic", output=tmp_path / "out", mass_mg=10.0, dpi=40))

    files = export_vsm_report(result.directory, tmp_path / "report", formats=("docx", "pdf"), dpi=80)

    assert [path.suffix for path in files] == [".docx", ".pdf"]
    assert all(path.is_file() and path.stat().st_size > 0 for path in files)
