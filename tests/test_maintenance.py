"""归档只移动、不删除；预演必须零改动，清单可追溯。"""
import json
import shutil

import pytest

from core.maintenance import archive_runs, delete_runs, find_duplicates, scan_runs, select_runs
from run_maintenance import main


def make_run(root, sample, run="20260101T000000_abcd", status="success",
             date="2026-01-01T00:00:00+08:00", size=1024, raw_sha256="a" * 64,
             configuration=None, cache_version=1):
    directory = root / sample / run
    directory.mkdir(parents=True)
    (directory / "analysis_record.json").write_text(json.dumps(
        {"sample": sample, "run_id": run, "status": status, "analysis_date": date,
         "raw_sha256": raw_sha256, "analysis_cache_version": cache_version,
         "configuration": configuration or {"thickness_step_mm": .1}}),
        encoding="utf-8")
    (directory / "RL_matrix.csv").write_bytes(b"x" * size)
    return directory


def test_scan_and_selection(tmp_path):
    make_run(tmp_path, "old", status="failed")
    make_run(tmp_path, "new", date="2099-01-01T00:00:00+08:00")
    runs = scan_runs(tmp_path)
    assert {run["sample"] for run in runs} == {"old", "new"}
    assert all(run["size_bytes"] >= 1024 for run in runs)
    assert [run["sample"] for run in select_runs(runs, older_than_days=30)] == ["old"]
    assert [run["sample"] for run in select_runs(runs, status="failed")] == ["old"]


def test_scan_skips_data_and_archive(tmp_path):
    run = make_run(tmp_path, "s")
    (run / "figures" / "RL.png.data").mkdir(parents=True)
    (run / "figures" / "RL.png.data" / "01.csv").write_text("x", encoding="utf-8")
    archived = make_run(tmp_path / "_archive", "s2")
    runs = scan_runs(tmp_path)
    assert [run["sample"] for run in runs] == ["s"]
    assert archived.exists()


def test_dry_run_moves_nothing(tmp_path):
    source = make_run(tmp_path, "s")
    report = archive_runs(scan_runs(tmp_path), tmp_path, apply=False)
    assert report["status"] == "planned" and report["total_bytes"] >= 1024
    assert source.is_dir() and not (tmp_path / "_archive").exists()


def test_apply_moves_run_writes_manifest_and_cleans_empty_parent(tmp_path):
    source = make_run(tmp_path, "s")
    report = archive_runs(scan_runs(tmp_path), tmp_path, apply=True)
    target = tmp_path / "_archive" / "s" / source.name
    assert report["status"] == "archived"
    assert not source.exists() and target.joinpath("analysis_record.json").is_file()
    assert not (tmp_path / "s").exists()  # 空的样品目录被清理
    manifest = json.loads((tmp_path / "_archive" / "archive_manifest.json").read_text(encoding="utf-8"))
    assert manifest["archives"][-1]["runs"][0]["relative"] == source.relative_to(tmp_path).as_posix()


def test_archive_root_inside_run_refused(tmp_path):
    source = make_run(tmp_path, "s")
    runs = scan_runs(tmp_path)
    with pytest.raises(ValueError, match="不能位于"):
        archive_runs(runs, tmp_path, source / "nested")


def test_archive_failure_is_isolated_and_recorded(tmp_path, monkeypatch):
    good = make_run(tmp_path, "good")
    bad = make_run(tmp_path, "bad")
    import core.maintenance as module
    original = module.shutil.move
    def move(source, target):
        if "bad" in str(source):
            raise OSError("locked")
        original(source, target)
    monkeypatch.setattr(module.shutil, "move", move)
    report = archive_runs(scan_runs(tmp_path), tmp_path, apply=True)
    assert report["status"] == "partial" and len(report["failures"]) == 1
    assert not good.exists() and bad.exists()


def test_find_duplicates_keeps_newest(tmp_path):
    make_run(tmp_path, "s", run="20260101T000000_old", date="2026-01-01T00:00:00+08:00", size=100)
    make_run(tmp_path, "s", run="20260201T000000_new", date="2026-02-01T00:00:00+08:00", size=100)
    groups = find_duplicates(scan_runs(tmp_path))
    assert len(groups) == 1 and groups[0]["count"] == 2
    assert groups[0]["keep"].endswith("20260201T000000_new")
    assert groups[0]["reclaimable_bytes"] >= 100


def test_find_duplicates_keeps_engine_versions_separate(tmp_path):
    make_run(tmp_path, "s", run="old_engine", cache_version=1)
    make_run(tmp_path, "s", run="new_engine", cache_version=2)
    assert find_duplicates(scan_runs(tmp_path)) == []


def test_delete_dry_run_then_recycle(tmp_path):
    source = make_run(tmp_path, "s")
    delete_runs(scan_runs(tmp_path), tmp_path, apply=False, recycler=lambda p: None)
    assert source.is_dir()
    calls = []
    report = delete_runs(scan_runs(tmp_path), tmp_path, apply=True,
                         recycler=lambda path: (calls.append(path), shutil.rmtree(path)))
    assert report["status"] == "deleted" and not source.exists()
    assert calls and calls[0] == source.resolve()
    manifest = json.loads((tmp_path / "deletion_manifest.json").read_text(encoding="utf-8"))
    assert manifest["deletions"][-1]["runs"][0]["relative"] == source.relative_to(tmp_path).as_posix()


def test_delete_failure_is_isolated(tmp_path):
    good = make_run(tmp_path, "good")
    bad = make_run(tmp_path, "bad")
    def recycler(path):
        if "bad" in str(path):
            raise OSError("locked")
        shutil.rmtree(path)
    report = delete_runs(scan_runs(tmp_path), tmp_path, apply=True, recycler=recycler)
    assert report["status"] == "partial" and len(report["failures"]) == 1
    assert not good.exists() and bad.exists()


def test_cli_delete_preview_keeps_files(tmp_path, capsys):
    make_run(tmp_path, "s")
    assert main(["--root", str(tmp_path), "--older-than", "0", "--delete"]) == 0
    assert "预演" in capsys.readouterr().out and (tmp_path / "s").is_dir()


def test_gui_archive_previews_then_moves(qtbot, tmp_path, monkeypatch):
    make_run(tmp_path, "old")
    from gui.pages import results_page as module
    page = module.ResultsPage(); qtbot.addWidget(page)
    page.folder = str(tmp_path)
    scanned = []
    monkeypatch.setattr(module.QInputDialog, "getInt", staticmethod(lambda *a, **k: (0, True)))
    monkeypatch.setattr(module.QMessageBox, "question",
                        staticmethod(lambda *a, **k: module.QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(page, "scan", lambda folder: scanned.append(folder))
    page.archive_old()
    qtbot.waitUntil(lambda: (tmp_path / "_archive" / "old").exists(), timeout=20000)
    qtbot.waitUntil(lambda: scanned == [str(tmp_path)], timeout=20000)
    assert not page.busy


def test_cli_defaults_to_preview(tmp_path, capsys):
    make_run(tmp_path, "s")
    assert main(["--root", str(tmp_path), "--older-than", "0"]) == 0
    output = capsys.readouterr().out
    assert "预演" in output and (tmp_path / "s").is_dir()
