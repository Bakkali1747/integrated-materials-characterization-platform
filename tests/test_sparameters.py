"""首行数值来自用户明确提供的真实片段；其余测试数据为合成，不依赖本机真实文件。"""

import hashlib
import json
from dataclasses import replace

import numpy as np
import pytest

from core.sparameter_mapping import SParameterMapping, load_sparameter_mapping
from core.sparameter_parser import read_sparameters
from core.sparameters import SParameterTolerances, analyze_sparameters
from run_sparameters import analyze_sparameter_file

FIRST = [2., -.053130, -.104635, -.632848, -.737062, -.634399, -.734638, .069938, .067728]
SHORT = SParameterMapping(expected_points=None, expected_frequency_start_ghz=None,
                          expected_frequency_stop_ghz=None, expected_frequency_step_ghz=None)


def write_fixture(path, rows, encoding="gb18030", header=None):
    header = header or '<Cluster><Name>夹具</Name><DBL><Name>D</Name><Val>2</Val></DBL></Cluster>'
    text = header+"\r\n\r\n"+"\r\n".join("\t".join(str(v) for v in row) for row in rows)+"\r\n"
    path.write_bytes(text.encode(encoding))
    return path


def test_real_first_row_regression(tmp_path):
    sample = read_sparameters(write_fixture(tmp_path/"first.sdat", [FIRST]), SHORT)
    expected = {"S11": -.053130-.104635j, "S21": -.632848-.737062j,
                "S12": -.634399-.734638j, "S22": .069938+.067728j}
    for name, value in expected.items():
        assert sample.s_parameters[name][0] == value
    table, _ = analyze_sparameters(sample.frequency_ghz, sample.s_parameters)
    row = table.iloc[0]
    assert row.frequency_ghz == 2
    assert row.S11_magnitude == pytest.approx(.11735, abs=5e-6)
    assert row.S11_db == pytest.approx(-18.61, abs=.005)
    assert row.S21_magnitude == pytest.approx(.97147, abs=5e-6)
    assert row.S21_db == pytest.approx(-.251, abs=.0005)
    assert row.R == pytest.approx(.013771280125, abs=1e-14)
    assert row["T"] == pytest.approx(.943756982948, abs=1e-14)
    assert row.A == pytest.approx(.042471736927, abs=1e-14)
    assert row.A == pytest.approx(.04247, abs=5e-6)


def test_full_candidate_grid_and_metadata(tmp_path):
    rows = [[2+.08*i, *FIRST[1:]] for i in range(201)]
    path = write_fixture(tmp_path/"full.sdat", rows)
    raw = path.read_bytes()
    data = read_sparameters(path)
    assert data.metadata["encoding_used"] == "gb18030"
    assert data.metadata["schema_status"] == "candidate_high_confidence"
    assert "夹具" in data.metadata["metadata_xml"]
    assert data.metadata["source_rows"] == list(range(3,204))
    assert data.raw_columns.shape == (201,9)
    np.testing.assert_allclose(data.frequency_ghz, np.linspace(2,18,201))
    assert path.read_bytes() == raw


def test_mapping_swap_is_configuration_not_computation(tmp_path):
    path = write_fixture(tmp_path/"first.sdat", [FIRST])
    mapping = replace(SHORT, schema_status="unverified", complex_columns={"S11":[1,2],"S21":[5,6],"S12":[3,4],"S22":[7,8]})
    data = read_sparameters(path, mapping)
    assert data.s_parameters["S21"][0] == -.634399-.734638j
    table, _ = analyze_sparameters(data.frequency_ghz, data.s_parameters)
    assert table["T"].iloc[0] == pytest.approx(abs(-.634399-.734638j)**2)


def test_hz_frequency_configuration(tmp_path):
    row = [2e9, *FIRST[1:]]
    data = read_sparameters(write_fixture(tmp_path/"hz.sdat", [row]), replace(SHORT, frequency_unit="Hz"))
    assert data.frequency_ghz[0] == 2.


@pytest.mark.parametrize("encoding", ["gb18030", "gbk", "utf-8-sig"])
def test_encoding_options(tmp_path, encoding):
    data = read_sparameters(write_fixture(tmp_path/"enc.sdat", [FIRST], encoding), SHORT, encoding=encoding)
    assert "夹具" in data.metadata["metadata_xml"]


def test_utf8_without_bom_is_not_misread_as_gb18030(tmp_path):
    path = write_fixture(tmp_path/"utf8.sdat", [FIRST], encoding="utf-8")
    data = read_sparameters(path, SHORT)
    assert data.metadata["encoding_used"] == "utf-8-sig"
    assert "夹具" in data.metadata["metadata_xml"]
    assert "\ufffd" not in data.metadata["metadata_xml"]


@pytest.mark.parametrize("kind", ["missing", "nan", "infinity", "extra", "duplicate", "reversed", "blank"])
def test_bad_numeric_data_refused(tmp_path, kind):
    rows = [FIRST.copy(), [2.08,*FIRST[1:]]]
    if kind == "missing": rows[0][3] = ""
    if kind == "nan": rows[0][3] = "NaN"
    if kind == "infinity": rows[0][3] = "inf"
    if kind == "extra": rows[0].append(123)
    if kind == "duplicate": rows[1][0] = 2
    if kind == "reversed": rows.reverse()
    path = write_fixture(tmp_path/"bad.sdat", rows)
    if kind == "blank":
        text = path.read_bytes().decode("gb18030").replace("\r\n2.08", "\r\n\r\n2.08")
        path.write_bytes(text.encode("gb18030"))
    with pytest.raises(ValueError):
        read_sparameters(path, SHORT)


@pytest.mark.parametrize("kind", ["point_count", "endpoint", "step"])
def test_known_grid_completeness(tmp_path, kind):
    rows = [[2+.08*i,*FIRST[1:]] for i in range(201)]
    if kind == "point_count": rows.pop()
    if kind == "endpoint": rows[-1][0] = 18.01
    if kind == "step": rows[10][0] += .001
    with pytest.raises(ValueError):
        read_sparameters(write_fixture(tmp_path/"bad.sdat", rows))


@pytest.mark.parametrize("header", ["<Cluster><Name>broken</Name>", "<Other></Other>", '<!DOCTYPE Cluster><Cluster></Cluster>'])
def test_bad_header_refused(tmp_path, header):
    with pytest.raises(ValueError):
        read_sparameters(write_fixture(tmp_path/"header.sdat", [FIRST], header=header), SHORT)


@pytest.mark.parametrize("change", [{"schema_status":"manufacturer-confirmed"}, {"frequency_column":1}, {"frequency_unit":"unknown"}])
def test_schema_validation(change):
    with pytest.raises(ValueError):
        replace(SHORT, **change).validate()


def test_schema_json_roundtrip(tmp_path):
    path = tmp_path/"schema.json"
    path.write_text(json.dumps(SHORT.to_dict()))
    assert load_sparameter_mapping(path).to_dict() == SHORT.to_dict()


def test_phase_quadrants_and_zero():
    s = {name: np.array([1j,-1j,-1+0j,0j]) for name in ("S11","S21","S12","S22")}
    table, _ = analyze_sparameters([1,2,3,4], s)
    np.testing.assert_allclose(table.S11_phase_deg[:3], [90,-90,180])
    assert np.isnan(table.S11_phase_deg.iloc[3])
    assert np.isneginf(table.S11_db.iloc[3])


def test_slight_negative_absorption_warned_not_clipped():
    s = {"S11":np.array([0j]), "S21":np.array([np.sqrt(1+5e-7)+0j]),
         "S12":np.array([np.sqrt(1+5e-7)+0j]), "S22":np.array([0j])}
    table, qc = analyze_sparameters([2], s)
    assert table.A.iloc[0] < 0
    assert table.A_negative.iloc[0] and not table.A_negative_exceeds_tolerance.iloc[0]
    assert not table.energy_exceeds_tolerance.iloc[0]
    assert any("未 clip" in warning for warning in qc["warnings"])


def test_large_violations_flagged():
    s = {"S11": [1.1+0j], "S21": [.5+0j], "S12": [.1+0j], "S22": [1.2+0j]}
    table, qc = analyze_sparameters([2], s)
    assert qc["magnitude_violation_counts"]["S11"] == 1
    assert qc["energy_violation_count"] == 1
    assert qc["reciprocity"]["violation_count"] == 1
    assert table.A.iloc[0] == pytest.approx(-.46)


def test_reciprocity_tolerance_configuration():
    s = {"S11": [0j], "S21": [.5+0j], "S12": [.49+0j], "S22": [0j]}
    _, strict = analyze_sparameters([2], s, SParameterTolerances(reciprocity_atol=.001,reciprocity_rtol=0))
    _, loose = analyze_sparameters([2], s, SParameterTolerances(reciprocity_atol=.02,reciprocity_rtol=0))
    assert strict["reciprocity"]["violation_count"] == 1
    assert loose["reciprocity"]["violation_count"] == 0
    assert loose["reciprocity"]["real_correlation"] is None


def test_nonfinite_and_negative_tolerance_refused():
    s = {name:[0j] for name in ("S11","S21","S12","S22")}
    s["S11"] = [complex(np.nan)]
    with pytest.raises(ValueError): analyze_sparameters([2],s)
    with pytest.raises(ValueError): SParameterTolerances(energy_atol=-1).validate()


def test_workflow_records_candidate_and_preserves_source(tmp_path):
    path = write_fixture(tmp_path/"sample.sdat", [FIRST])
    original = path.read_bytes()
    first = analyze_sparameter_file(path, mapping=SHORT, output=tmp_path/"out", make_figures=False)
    second = analyze_sparameter_file(path, mapping=SHORT, output=tmp_path/"out", make_figures=False)
    assert first != second
    record = json.loads((first/"analysis_record.json").read_text(encoding="utf-8"))
    assert record["schema_status"] == "candidate_high_confidence" and record["status"] == "success"
    assert record["raw_sha256"] == hashlib.sha256(original).hexdigest()
    assert record["complex_convention"] == "Sij = real + j*imag"
    assert record["interpolation"] == record["clipping"] == "OFF"
    assert path.read_bytes() == original
    with np.load(first/"sparameters_complex.npz") as archive:
        assert archive["S11"][0] == -.053130-.104635j
        assert str(archive["schema_status"]) == "candidate_high_confidence"


def test_failed_run_has_record(tmp_path):
    path = write_fixture(tmp_path/"short.sdat", [FIRST])
    with pytest.raises(ValueError):
        analyze_sparameter_file(path, output=tmp_path/"out", make_figures=False)
    record_path = next((tmp_path/"out").rglob("analysis_record.json"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "failed" and "201" in record["error"]
