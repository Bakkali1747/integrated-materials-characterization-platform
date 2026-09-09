import hashlib
import json
import pytest
from run_analysis import analyze
from plotting.style import PlotStyle


@pytest.mark.parametrize("threshold", [-5, 0])
def test_traceable_run_and_no_overwrite(tmp_path, frame, threshold):
    path = tmp_path / "input.csv"
    frame.to_csv(path, index=False)
    original = path.read_bytes()
    options = dict(output=tmp_path/"output", imaginary_convention="loss", thickness_max=1.1,
                   thickness_step=.1, style=PlotStyle(dpi=40), threshold=threshold)
    first = analyze(path, **options)
    second = analyze(path, **options)
    assert first != second
    record = json.loads((first/"analysis_record.json").read_text(encoding="utf-8"))
    assert record["status"] == "success"
    assert record["source"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert record["missing_data_interpolation"] == "OFF"
    assert record["eab_threshold_crossing"] == "linear"
    assert record["standard_eab_threshold_db"] == -10
    assert record["rl_threshold_db"] == threshold
    assert "pending" in record["validation_status"]
    assert record["thickness_grid_mm"] == [1, 1.1]
    assert path.read_bytes() == original
    summary = json.loads((first/"summary.json").read_text())
    assert summary["standard_eab"]["metric"] == "EAB"
    assert "EAB" not in summary["selected_threshold_bandwidth"]["metric"]
    for relative, digest in record["artifacts_sha256"].items():
        assert hashlib.sha256((first/relative).read_bytes()).hexdigest() == digest


def test_failure_is_recorded(tmp_path, frame):
    path = tmp_path/"bad.csv"
    frame.loc[1, "mu_imag"] = float("nan")
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError):
        analyze(path, output=tmp_path/"output", imaginary_convention="loss")
    files = list((tmp_path/"output").rglob("analysis_record.json"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8"))
    assert record["status"] == "failed" and "mu_imag" in record["error"]
    assert record["raw_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
