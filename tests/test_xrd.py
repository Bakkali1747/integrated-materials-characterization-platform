"""XRD 解析、峰检测、Scherrer 尺寸、背景扣除、参考匹配与运行产物。"""

import math

import numpy as np
import pytest

from core.xrd import analyze_xrd, inspect_xrd_table, read_xrd, read_xrd_reference, suggest_xrd_columns
from core.xrd_service import XRDConfig, execute, load_completed_xrd_run
from export.xrd_report import export_xrd_report


def pattern_rows(*, peaks=((20.0, 500.0, .08), (30.0, 300.0, .10), (40.0, 200.0, .12)),
                 base=100.0, slope=.5, low=10.0, high=80.0, step=.02):
    x = np.arange(low, high + step / 2, step)
    y = base + slope * x
    for position, amplitude, sigma in peaks:
        y = y + amplitude * np.exp(-((x - position) / sigma) ** 2)
    return x, y


def write_csv(path, **values):
    x, y = pattern_rows(**values)
    path.write_text("two_theta_deg,intensity\n" + "\n".join(f"{a:.4f},{b:.6f}" for a, b in zip(x, y)),
                    encoding="utf-8")
    return path


def write_raw4_text(path, *, sample="RAW Sample", points=20, start=20.0, step=.02,
                    wavelength=1.5418):
    lines = [";RAW4.00", "[RawHeader]", "Date=08/03/2026", "Time=20:23:19", "",
             "[HardwareConfiguration]", "Alpha1=1.5406", "Alpha2=1.54439",
             f"AlphaAverage={wavelength}", "", "[RangeHeader]", f"Start={start}",
             f"Increment={step}", f"ActuallyUsedLambda={wavelength}",
             f"NumberOfMeasuredData={points}", "", "[VarInfo]", "Type=SAMPLEID", "Flags=0",
             f"Value={sample}", "", "[Data]", "Angle, PSD,"]
    lines += [f"{start + index * step:.4f}, {10 + index}," for index in range(points)]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_read_bruker_raw4_text(tmp_path):
    path = write_raw4_text(tmp_path / "A.txt", points=40)
    data = read_xrd(path)

    assert data.metadata["parser"] == "bruker-raw4-text-v1"
    assert data.metadata["wavelength_angstrom"] == pytest.approx(1.5418)
    assert data.metadata["wavelength_source"] == "ActuallyUsedLambda"
    assert data.metadata["column_map"] == {"two_theta": "Angle", "intensity": "PSD"}
    assert data.metadata["raw4_sample_id"] == "RAW Sample"
    assert len(data.frame) == 40
    assert data.frame["two_theta_deg"].iloc[0] == pytest.approx(20.0)
    assert data.frame["intensity"].iloc[-1] == 49


def write_raw4_binary(path, *, points=100, start=10.0, step=.02, wavelength=1.5406,
                      counts=None):
    """构造一个已观察结构的 RAW4 二进制：几何签名 + 末尾 float32 计数。"""
    import struct

    counts = list(range(10, 10 + points)) if counts is None else list(counts)
    header = bytearray(200)
    struct.pack_into("<2d", header, 100, start, step)
    struct.pack_into("<i", header, 116, points)
    struct.pack_into("<d", header, 140, wavelength)
    path.write_bytes(bytes(header) + struct.pack(f"<{points}f", *counts))
    return path


def test_read_bruker_raw4_binary_direct(tmp_path):
    path = write_raw4_binary(tmp_path / "A.raw", points=120, counts=[5] * 120)
    data = read_xrd(path)

    assert data.metadata["parser"] == "bruker-raw4-binary-v1"
    assert data.metadata["raw_binary_direct"] is True
    assert data.metadata["wavelength_angstrom"] == pytest.approx(1.5406)
    assert len(data.frame) == 120
    assert data.frame["intensity"].tolist() == [5.0] * 120
    assert data.frame["two_theta_deg"].iloc[0] == pytest.approx(10.0)
    assert data.frame["two_theta_deg"].iloc[-1] == pytest.approx(10.0 + .02 * 119)
    assert not any("同名 TXT" in warning for warning in data.warnings)


def test_binary_raw_uses_same_stem_txt_companion(tmp_path):
    raw = tmp_path / "A.raw"
    raw.write_bytes(b"\x00\x01\x02binary-header" + b"\x00" * 64)
    write_raw4_text(tmp_path / "A.txt", points=30, sample="companion")

    data = read_xrd(raw)

    assert data.metadata["raw_binary"] is True
    assert data.metadata["parser"] == "bruker-raw4-text-v1"
    assert data.metadata["sha256"] == __import__("hashlib").sha256(raw.read_bytes()).hexdigest()
    assert data.metadata["companion_path"].endswith("A.txt")
    assert data.metadata["companion_sha256"]
    assert any("同名 TXT" in warning for warning in data.warnings)
    assert len(data.frame) == 30


def test_binary_raw_without_companion_is_rejected(tmp_path):
    raw = tmp_path / "B.raw"
    raw.write_bytes(b"\x00\x01binary" + b"\x00" * 32)
    with pytest.raises(ValueError, match="同名 .txt"):
        read_xrd(raw)


def test_inspect_bruker_raw4_exposes_wavelength(tmp_path):
    path = write_raw4_text(tmp_path / "A.raw", points=10)
    preview = inspect_xrd_table(path)
    assert preview["metadata"]["wavelength_angstrom"] == pytest.approx(1.5418)
    assert preview["metadata"]["parser"] == "bruker-raw4-text-v1"
    assert "Angle" in preview["columns"] and "PSD" in preview["columns"]


def test_read_xrd_csv_and_headerless_xy(tmp_path):
    csv_path = write_csv(tmp_path / "pattern.csv")
    data = read_xrd(csv_path)
    assert data.metadata["column_map"] == {"two_theta": "two_theta_deg", "intensity": "intensity"}
    assert len(data.frame) == len(pattern_rows()[0])

    x, y = pattern_rows()
    xy_path = tmp_path / "pattern.xy"
    xy_path.write_text("# synthetic\n" + "\n".join(f"{a:.4f} {b:.6f}" for a, b in zip(x[:100], y[:100])),
                       encoding="utf-8")
    xy = read_xrd(xy_path)
    assert list(xy.frame.columns) == ["source_row", "two_theta_deg", "intensity"]
    assert xy.metadata["has_header"] is False


def test_read_xrd_rejects_non_increasing_angles(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("2theta,intensity\n20,10\n19,12\n21,13\n22,14\n23,15\n", encoding="utf-8")
    with pytest.raises(ValueError, match="严格递增"):
        read_xrd(path)


def test_suggest_and_inspect_columns(tmp_path):
    path = write_csv(tmp_path / "pattern.csv")
    preview = inspect_xrd_table(path)
    assert preview["columns"] == ["two_theta_deg", "intensity"]
    assert suggest_xrd_columns(["2θ", "Intensity"]) == ("2θ", "Intensity")
    assert suggest_xrd_columns(["angle", "counts"]) == ("angle", "counts")


def test_detect_peaks_fwhm_scherrer(tmp_path):
    path = write_csv(tmp_path / "pattern.csv")
    data = read_xrd(path)
    result = analyze_xrd(data, wavelength_angstrom=1.5406, k_factor=.9, min_prominence_relative=.01, smoothing_points=1)

    assert result["status"] == "success"
    peaks = result["peaks"]
    assert [round(peak["two_theta_deg"], 2) for peak in peaks] == [20.0, 30.0, 40.0]
    first = peaks[0]
    assert first["fwhm_deg"] == pytest.approx(2 * math.sqrt(math.log(2)) * .08, abs=.01)
    theta = math.radians(first["two_theta_deg"] / 2)
    expected_d = 1.5406 / (2 * math.sin(theta))
    assert first["d_angstrom"] == pytest.approx(expected_d, rel=1e-6)
    expected_size = .9 * 1.5406 / (math.radians(first["fwhm_deg"]) * math.cos(theta)) / 10
    assert first["crystallite_size_nm"] == pytest.approx(expected_size, rel=1e-6)
    assert first["relative_intensity_pct"] == pytest.approx(100.0)
    assert result["quality"]["smoothing"] == "OFF" and result["quality"]["sorting"] == "preserved"


def test_linear_background_subtraction_recovers_peaks(tmp_path):
    path = write_csv(tmp_path / "pattern.csv")
    data = read_xrd(path)
    result = analyze_xrd(data, smoothing_points=1, background_mode="linear", background_left=(10.0, 15.0),
                         background_right=(75.0, 80.0), min_prominence_relative=.01)

    background = result["background"]
    assert background["mode"] == "linear"
    assert background["slope"] == pytest.approx(.5, rel=.05)
    assert [round(peak["two_theta_deg"], 2) for peak in result["peaks"]] == [20.0, 30.0, 40.0]
    assert result["peaks"][0]["corrected_intensity"] == pytest.approx(500.0, rel=.2)


def test_min_prominence_filters_weak_peak(tmp_path):
    path = write_csv(tmp_path / "pattern.csv", peaks=((20.0, 500.0, .08), (30.0, 5.0, .10)))
    data = read_xrd(path)
    result = analyze_xrd(data, min_prominence_relative=.02, smoothing_points=1)
    assert [round(peak["two_theta_deg"], 2) for peak in result["peaks"]] == [20.0]


def test_no_peaks_is_not_computable(tmp_path):
    path = tmp_path / "flat.csv"
    x = np.arange(10, 80.01, .05)
    path.write_text("2theta,intensity\n" + "\n".join(f"{a:.4f},100" for a in x), encoding="utf-8")
    data = read_xrd(path)
    result = analyze_xrd(data)
    assert result["status"] == "not_computable"
    assert result["peaks"] == []


def test_reference_phase_matching(tmp_path):
    path = write_csv(tmp_path / "pattern.csv")
    reference = tmp_path / "reference.csv"
    reference.write_text("two_theta,intensity,phase\n20,100,alpha\n30,60,alpha\n40,40,alpha\n"
                         "35,100,beta\n", encoding="utf-8")
    data = read_xrd(path)
    records = read_xrd_reference(reference)
    result = analyze_xrd(data, reference=records, match_tolerance_deg=.2, min_prominence_relative=.01, smoothing_points=1)

    assert result["reference_matching"][0]["phase"] == "alpha"
    assert result["reference_matching"][0]["score"] == pytest.approx(1.0)
    assert result["reference_matching"][0]["matched_count"] == 3


def test_execute_writes_artifacts_and_reloads(tmp_path):
    path = write_csv(tmp_path / "pattern.csv")
    config = XRDConfig(path=path, name="synthetic", output=tmp_path / "out", dpi=40,
                       wavelength_angstrom=1.5406, min_prominence_relative=.01)
    result = execute(config)

    assert result.record["status"] == "success"
    assert result.record["analysis_kind"] == "xrd_peaks"
    for name in ("parsed_data.csv", "xrd_peaks.csv", "xrd_peaks.json", "analysis_record.txt"):
        assert (result.directory / name).is_file()
    saved = load_completed_xrd_run(result.directory)
    assert len(saved["metrics"]["peaks"]) == 3
    assert len(saved["table"]) == len(pattern_rows()[0])


def test_export_xrd_report(tmp_path):
    path = write_csv(tmp_path / "pattern.csv")
    result = execute(XRDConfig(path=path, name="synthetic", output=tmp_path / "out", dpi=40,
                               wavelength_angstrom=1.5406, min_prominence_relative=.01))
    files = export_xrd_report(result.directory, tmp_path / "report", formats=("docx", "pdf"), dpi=80)
    assert [item.suffix for item in files] == [".docx", ".pdf"]
    assert all(item.is_file() and item.stat().st_size > 0 for item in files)
