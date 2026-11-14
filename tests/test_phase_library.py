"""COD 物相库 search-match 与 XRD service 集成测试。"""

import json
import sqlite3

import numpy as np

from core.phase_library import PhaseLibrary
from core.xrd_service import XRDConfig, execute


def write_library(path):
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE phases(id INTEGER PRIMARY KEY, formula TEXT, mineral TEXT,
                            spacegroup TEXT, quality TEXT, rir REAL, nlines INTEGER);
        CREATE TABLE lines(phase_id INTEGER, d REAL, intensity REAL);
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
    """)
    connection.executemany("INSERT INTO phases VALUES(?,?,?,?,?,?,?)", [
        (1, "Fe", "Iron", "I m -3 m", "C", 1.0, 3),
        (2, "Cr", None, "I m -3 m", "C", 1.0, 3),
        (3, "SiO2", "Quartz", "P 32 2 1", "C", 1.0, 2),
    ])
    connection.executemany("INSERT INTO lines VALUES(?,?,?)", [
        (1, 2.026, 1000), (1, 1.433, 200), (1, 1.170, 150),
        (2, 2.039, 1000), (2, 1.442, 180), (2, 1.178, 120),
        (3, 3.343, 1000), (3, 4.257, 200),
    ])
    connection.executemany("INSERT INTO meta VALUES(?,?)",
                           [("phases", "3"), ("license", "CC-BY-4.0")])
    connection.commit()
    connection.close()
    return path


def test_phase_library_ranks_matching_phase(tmp_path):
    library = PhaseLibrary(write_library(tmp_path / "library.sqlite"))
    peaks = [
        {"center_deg": 44.7, "relative_intensity_pct": 100.0, "d_angstrom": 2.026},
        {"center_deg": 65.0, "relative_intensity_pct": 20.0, "d_angstrom": 1.433},
        {"center_deg": 82.35, "relative_intensity_pct": 15.0, "d_angstrom": 1.170},
    ]
    results = library.search(peaks, 1.5406, tolerance_deg=.1)
    assert results[0]["formula"] == "Fe"
    assert results[0]["score"] > .8
    assert results[0]["matched_count"] == 3


def test_phase_library_respects_tolerance(tmp_path):
    library = PhaseLibrary(write_library(tmp_path / "library.sqlite"))
    peaks = [{"center_deg": 20.0, "relative_intensity_pct": 100.0, "d_angstrom": 4.4}]
    assert library.search(peaks, 1.5406, tolerance_deg=.1) == []


def test_xrd_service_records_phase_library_matches(tmp_path):
    library = write_library(tmp_path / "library.sqlite")
    path = tmp_path / "pattern.csv"
    x = np.arange(10.0, 90.0, .02)
    y = 10.0
    for center, height, width in ((44.7, 800.0, .2), (65.0, 180.0, .3), (82.0, 120.0, .4)):
        y = y + height * np.exp(-((x - center) / width) ** 2)
    rows = ["two_theta_deg,intensity"] + [f"{a:.4f},{b:.6f}" for a, b in zip(x, y)]
    path.write_text("\n".join(rows), encoding="utf-8")
    result = execute(XRDConfig(
        path=path, name="fe", output=tmp_path / "out", wavelength_angstrom=1.5406,
        min_prominence_relative=.01, smoothing_points=1, phase_library_path=library,
        phase_match_tolerance_deg=.1, dpi=30))
    assert result.analysis["library_matches"][0]["formula"] == "Fe"
    payload = json.loads((result.directory / "xrd_peaks.json").read_text(encoding="utf-8"))
    assert payload["library_matches"]
    assert (result.directory / "phase_library_matching.json").is_file()
    assert result.record["quality"]["phase_library"]["phase_count"] == 3
