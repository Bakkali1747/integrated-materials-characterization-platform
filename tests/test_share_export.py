"""分享副本不能泄露绝对路径，也不能改动原运行。"""
import json

import pytest

from export.share_export import export_shareable, redact


def make_run(tmp_path):
    run = tmp_path / "output" / "sample_S" / "20260101T000000_abcd"
    run.mkdir(parents=True)
    record = {"sample": "S", "status": "success", "raw_sha256": "a" * 64,
              "validation_status": "pending", "raw_file": r"C:\Users\alice\data\S.csv",
              "source": {"raw_file": r"C:\Users\alice\data\S.csv", "sha256": "a" * 64},
              "configuration": {"output": r"C:\Users\alice\results"},
              "warnings": ["示例警告"]}
    (run / "analysis_record.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    (run / "summary.json").write_text('{"x": 1}', encoding="utf-8")
    (run / "sources.csv").write_text("sample,raw_file\nS," + r"C:\Users\alice\data\S.csv" + "\n", encoding="utf-8")
    return run


def test_redact_replaces_absolute_paths_only():
    assert redact(r"C:\Users\alice\data\S.csv") == "S.csv"
    assert redact("/home/alice/S.csv") == "S.csv"
    assert redact("pending") == "pending"
    assert redact({"raw_file": r"C:\a\b.csv"}) == {"raw_file": "b.csv"}


def test_export_shareable_removes_absolute_paths(tmp_path):
    run = make_run(tmp_path)
    original = (run / "analysis_record.json").read_bytes()
    output = export_shareable(run, tmp_path / "share")
    record = json.loads((output / "analysis_record.json").read_text(encoding="utf-8"))
    assert record["raw_file"] == "S.csv"
    assert record["source"]["raw_file"] == "S.csv"
    assert record["configuration"]["output"] == "results"
    assert "alice" not in (output / "analysis_record.json").read_text(encoding="utf-8")
    assert (output / "summary.json").is_file() and (output / "README_SHARE.txt").is_file()
    sources = (output / "sources.csv").read_text(encoding="utf-8-sig")
    assert "alice" not in sources and "S.csv" in sources
    manifest = json.loads((output / "share_manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"]["analysis_record.json"]
    assert (run / "analysis_record.json").read_bytes() == original
    assert run.joinpath("README_SHARE.txt").is_file() is False


def test_export_shareable_refuses_dirty_or_inside_targets(tmp_path):
    run = make_run(tmp_path)
    dirty = tmp_path / "share"
    dirty.mkdir(); (dirty / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="为空"):
        export_shareable(run, dirty)
    with pytest.raises(ValueError, match="不能位于"):
        export_shareable(run, run / "share")
