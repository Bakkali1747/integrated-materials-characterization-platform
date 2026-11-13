"""工作区 schema 版本、旧工作区迁移与拒绝不安全版本。"""

import json

import pytest

from core.common import SCHEMA_VERSION, WorkspaceRepository, WorkspaceSchemaError, workspace_schema
from gui.pages.workspace_page import WorkspacePage


def test_fresh_workspace_creates_current_schema(tmp_path):
    repository = WorkspaceRepository(tmp_path / "workspace")
    info = repository.schema_info()
    assert info["schema_version"] == SCHEMA_VERSION
    assert info["created"] is True and info["migrated"] is False
    value = json.loads((tmp_path / "workspace" / "workspace.json").read_text(encoding="utf-8"))
    assert value["schema_version"] == SCHEMA_VERSION


def test_legacy_workspace_is_migrated_without_rewriting_entities(tmp_path):
    root = tmp_path / "workspace"
    repository = WorkspaceRepository(root)
    project = repository.create_project("legacy")
    repository.create_sample(project.project_id, "sample", sample_id="S1")
    entities = {path: path.read_bytes() for path in root.rglob("*.json") if path.name != "workspace.json"}
    (root / "workspace.json").unlink()

    reopened = WorkspaceRepository(root)

    info = reopened.schema_info()
    assert info["schema_version"] == SCHEMA_VERSION
    assert info["migrated"] is True and info["previous_version"] == 0
    assert {path: path.read_bytes() for path in root.rglob("*.json") if path.name != "workspace.json"} == entities
    assert reopened.list_projects()[0].project_id == project.project_id
    assert reopened.list_samples(project.project_id)[0].sample_id == "S1"


def test_future_schema_version_is_rejected_without_modification(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    path = root / "workspace.json"
    original = {"schema_version": SCHEMA_VERSION + 1, "note": "created by a newer app"}
    path.write_text(json.dumps(original), encoding="utf-8")

    with pytest.raises(WorkspaceSchemaError, match="高于"):
        WorkspaceRepository(root)
    assert json.loads(path.read_text(encoding="utf-8")) == original


def test_corrupt_schema_file_is_rejected(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "workspace.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(WorkspaceSchemaError, match="无法读取"):
        WorkspaceRepository(root)


def test_corrupt_legacy_entity_blocks_migration(tmp_path):
    root = tmp_path / "workspace"
    project = root / "projects" / "prj_broken"
    project.mkdir(parents=True)
    (project / "project.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(WorkspaceSchemaError, match="损坏"):
        WorkspaceRepository(root)
    assert not (root / "workspace.json").exists()


def test_registered_migration_advances_schema_version(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    WorkspaceRepository(root)
    calls = []
    monkeypatch.setattr(workspace_schema, "SCHEMA_VERSION", SCHEMA_VERSION + 1)
    monkeypatch.setitem(workspace_schema.MIGRATIONS, SCHEMA_VERSION, lambda path: calls.append(path))

    reopened = WorkspaceRepository(root)

    info = reopened.schema_info()
    assert calls == [root.resolve()]
    assert info["schema_version"] == SCHEMA_VERSION + 1
    assert info["migrated"] is True and info["previous_version"] == SCHEMA_VERSION
    value = json.loads((root / "workspace.json").read_text(encoding="utf-8"))
    assert value["schema_version"] == SCHEMA_VERSION + 1
    assert value["migrated_from"] == SCHEMA_VERSION


def test_workspace_page_reports_schema_error_without_data_loss(qtbot, tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "workspace.json").write_text(json.dumps({"schema_version": SCHEMA_VERSION + 5}), encoding="utf-8")
    monkeypatch.setattr("gui.pages.workspace_page.user_data_root", lambda: tmp_path)

    page = WorkspacePage()
    qtbot.addWidget(page)

    assert page.repository is None
    assert "不可用" in page.schema_label.text()
    assert page.projects.rowCount() == 0
    assert not page.new_project_button.isEnabled()
    with pytest.raises(ValueError, match="工作区"):
        page.create_project("should not exist")
