"""安装版路径与来源适配，不重复测试科学公式。"""

import json
import sys
from pathlib import Path

import application_paths
from export.provenance import git_state


def test_source_data_root_unchanged(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert application_paths.user_data_root() == Path(__file__).resolve().parents[1]


def test_frozen_data_outside_install_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user"))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "readonly"), raising=False)
    assert application_paths.user_data_root() == tmp_path / "user/MicrowaveAbsorptionAnalyzer"
    assert application_paths.resource_root() == tmp_path / "readonly"


def test_packaged_git_uses_embedded_record(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    (tmp_path / "build_info.json").write_text(json.dumps({"commit": "a" * 40, "dirty": False}))
    monkeypatch.setattr("export.provenance.subprocess.check_output", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Git must not run")))
    assert git_state() == {"commit": "a" * 40, "dirty": False, "origin": "packaged_build"}


def test_missing_build_record_is_not_validated(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert git_state()["commit"] == "unavailable"
    assert git_state()["dirty"] == "unavailable"


def test_source_resources_do_not_depend_on_working_directory(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.chdir(tmp_path)
    assert (application_paths.resource_root() / "sample_data/synthetic_constant.csv").exists()
