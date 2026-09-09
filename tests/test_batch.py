import hashlib
import json
import numpy as np
import pandas as pd
import pytest
from openpyxl import load_workbook
from core.batch import discover_samples, load_manifest, validate_entries
from core.sdat_inspector import inspect_sdat
from export.excel_export import export_batch_excel
from run_batch import analyze_batch, compare_runs, summarize_sample
from plotting.style import PlotStyle


def test_discovery_snapshot_and_output_exclusion(tmp_path):
    (tmp_path/"group").mkdir()
    (tmp_path/"out").mkdir()
    for name in ("group/a.csv", "b.memp", "c.sdat", "readme.txt", "out/result.csv"):
        (tmp_path/name).write_text("test")
    entries, skipped = discover_samples(tmp_path, {"imaginary_convention": "loss"}, [tmp_path/"out"])
    assert {row["name"] for row in entries} == {"group/a", "b", "c"}
    assert skipped == ["readme.txt"]


def test_manifest_relative_paths_and_overrides(tmp_path):
    manifest = {"parser_defaults": {"imaginary_convention": "loss"},
                "analysis": {"curve_thickness": 2.5}, "samples": [{"name": "A", "path": "a.csv"},
                    {"name": "B", "path": "b.csv", "parser": {"imaginary_convention": "signed", "frequency_unit": "Hz"}}],
                "compare_samples": ["B"]}
    path = tmp_path/"manifest.json"
    path.write_text(json.dumps(manifest))
    entries, options, selected = load_manifest(path)
    assert entries[0]["path"] == str((tmp_path/"a.csv").resolve())
    assert entries[1]["parser"]["imaginary_convention"] == "signed"
    assert options["curve_thickness"] == 2.5 and selected == ["B"]


def test_duplicate_sample_names_refused():
    with pytest.raises(ValueError, match="重复"):
        validate_entries([{"name": "A", "path": "a.csv"}, {"name": "A", "path": "b.csv"}])


def test_sdat_structure_does_not_assign_meaning(tmp_path):
    path = tmp_path/"test.sdat"
    path.write_bytes(("<Cluster><Name>夹具</Name><DBL><Name>D</Name><Val>2</Val></DBL></Cluster>\n"
                      "2 1 2 3 4 5 6 7 8\n3 1 2 3 4 5 6 7 8\n").encode("gbk"))
    original = path.read_bytes()
    record, table = inspect_sdat(path)
    assert record["field_meanings"] == "unknown"
    assert record["frequency_unit"] == "unknown"
    assert list(table.columns) == [f"column_{i}" for i in range(1, 10)]
    assert record["source_rows"] == [2, 3]
    assert original == path.read_bytes()


def test_batch_partial_failure_native_grids_and_workbook(tmp_path, frame):
    a, b, bad = tmp_path/"a.csv", tmp_path/"b.csv", tmp_path/"bad.csv"
    frame.to_csv(a, index=False)
    variant = frame.iloc[[0, 2]].copy()
    variant.eps_imag *= 2
    variant.to_csv(b, index=False)
    damaged = frame.copy()
    damaged.loc[1, "mu_imag"] = np.nan
    damaged.to_csv(bad, index=False)
    entries = [{"name": name, "path": str(path), "parser": {"imaginary_convention": "loss"}} for name, path in (("A",a), ("B",b), ("bad",bad))]
    directory = analyze_batch(entries, output=tmp_path/"output", analysis_options={"thickness_min": 1, "thickness_max": 1.1, "thickness_step": .1}, style=PlotStyle(dpi=35))
    record = json.loads((directory/"batch_record.json").read_text(encoding="utf-8"))
    assert record["status"] == "partial_failure" and record["success_count"] == 2
    assert not record["comparison"]["identical_frequency_grids"]
    assert record["comparison"]["excluded_failed_samples"] == ["bad"]
    comparison = pd.read_csv(directory/"comparison"/"eps_real.csv")
    assert comparison.groupby("sample").size().to_dict() == {"A": 3, "B": 2}
    workbook = load_workbook(directory/"all_samples_summary.xlsx", data_only=False)
    assert workbook.sheetnames == ["Summary", "RL_minima", "EAB_bands", "Provenance"]
    assert workbook["Summary"]["A4"].value == "bad"
    assert workbook["Summary"]["C4"].value is None
    assert isinstance(workbook["Summary"]["C2"].value, float)
    assert workbook["Summary"].freeze_panes == "B2"
    first_run = next(directory.glob("samples/0001/sample_*/20*"))
    with (first_run/"loss_parameters.csv").open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="已改变"):
        compare_runs([("A", first_run)], tmp_path/"altered_compare", PlotStyle(dpi=35), 2.)


def test_summary_preserves_all_tied_points(tmp_path):
    record = {"status": "success", "global_minima": [{"rl_min_db": -20, "frequency_ghz": 4, "thickness_mm": d,
                "at_frequency_boundary": False, "at_thickness_boundary": False} for d in (1,2)],
              "maximum_eab_ghz": 2, "maximum_eab_details": [{"thickness_mm": d, "widest_bands": [
                  {"start_ghz": 2, "end_ghz": 4, "width_ghz": 2, "touches_lower_boundary": True, "touches_upper_boundary": False}]} for d in (2,3)],
              "validation_status": "pending", "frequency_range_ghz": [2,18]}
    (tmp_path/"analysis_record.json").write_text(json.dumps(record))
    summary, points, bands, _ = summarize_sample("A", tmp_path)
    assert len(points) == len(bands) == 2
    assert summary["rl_min_tie_count"] == summary["maximum_eab_thickness_tie_count"] == 2


def test_excel_sample_name_is_literal_not_formula(tmp_path):
    path = tmp_path/"safe.xlsx"
    export_batch_excel(path, [{"sample": "=1+1", "status": "failed"}], [], [], [["A", "note", "=1+1"]])
    workbook = load_workbook(path, data_only=False)
    assert workbook["Summary"]["A2"].data_type == "s"
    assert workbook["Provenance"]["C2"].data_type == "s"
