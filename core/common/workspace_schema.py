"""工作区 schema 版本与迁移。

旧工作区（v0.13/v0.14，没有 `workspace.json`）在首次打开时按 v0 处理：只读校验
全部实体 JSON，然后写入版本标记，不改写已有项目/样品/测试/运行文件。

未来版本或损坏文件不会被静默改写：程序拒绝打开并给出明确原因，避免降级覆盖。
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from core import __version__

SCHEMA_VERSION = 1
SCHEMA_FILENAME = "workspace.json"
LAYOUT = "project/sample/measurement/analysis_run"


class WorkspaceSchemaError(ValueError):
    """工作区版本或结构无法安全处理；不会自动修改工作区内容。"""


@dataclass(frozen=True)
class WorkspaceSchema:
    """一次打开工作区的 schema 结果。"""
    path: Path
    version: int
    previous_version: int | None = None
    migrated: bool = False
    created: bool = False


Migration = Callable[[Path], None]


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _atomic_write(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise WorkspaceSchemaError(f"无法读取工作区版本文件 {path}：{error}") from error
    if not isinstance(value, dict):
        raise WorkspaceSchemaError(f"工作区版本文件 {path} 不是 JSON 对象。")
    return value


def _entity_files(root: Path):
    """列出所有需要校验的工作区 JSON；不使用数据库。"""
    yield from root.glob("projects/*/project.json")
    yield from root.glob("projects/*/samples/*/sample.json")
    yield from root.glob("projects/*/samples/*/measurements/*.json")
    yield from root.glob("projects/*/samples/*/analyses/*.json")


def _migrate_v0_to_v1(root: Path) -> None:
    """v0（无版本文件）→ v1：布局未变，只验证每个实体文件可解析。"""
    for path in _entity_files(root):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise WorkspaceSchemaError(f"旧工作区实体文件损坏，未自动迁移：{path}（{error}）") from error
        if not isinstance(value, dict):
            raise WorkspaceSchemaError(f"旧工作区实体文件不是 JSON 对象，未自动迁移：{path}")


# 从版本 n 升级到 n+1。当前只有 v0 → v1；后续结构变化在此追加，并递增 SCHEMA_VERSION。
MIGRATIONS: dict[int, Migration] = {0: _migrate_v0_to_v1}


def _new_record(*, previous_version: int | None, migrated: bool) -> dict:
    now = _now()
    record = {"schema_version": SCHEMA_VERSION, "layout": LAYOUT, "software_version": __version__,
              "created_at": now}
    if migrated:
        record.update(previous_schema_version=previous_version, migrated_from=previous_version, migrated_at=now)
    return record


def initialize_schema(root: str | Path) -> WorkspaceSchema:
    """打开工作区前读取或建立版本标记，并按需执行已登记的迁移。

    - 无版本文件且没有项目：新建当前版本工作区。
    - 无版本文件但已有项目：视为 v0，校验后迁移到当前版本。
    - 版本高于程序支持：抛出 WorkspaceSchemaError，绝不降级覆盖。
    """
    root = Path(root).expanduser().resolve()
    path = root / SCHEMA_FILENAME
    if path.is_file():
        record = _read(path)
        version = record.get("schema_version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise WorkspaceSchemaError(
                f"工作区版本文件 {path} 的 schema_version 无效：{version!r}。")
        if version > SCHEMA_VERSION:
            raise WorkspaceSchemaError(
                f"工作区 schema 版本 {version} 高于当前程序支持的 {SCHEMA_VERSION}；"
                "请使用更新版本的程序打开。现有数据未被修改。")
        previous = version
        migrated = version < SCHEMA_VERSION
        while version < SCHEMA_VERSION:
            migration = MIGRATIONS.get(version)
            if migration is None:
                raise WorkspaceSchemaError(f"缺少从 schema v{version} 升级的迁移步骤。")
            migration(root)
            version += 1
        if migrated:
            record.update(schema_version=version, previous_schema_version=previous, migrated_from=previous,
                          migrated_at=_now(), software_version=__version__)
            _atomic_write(path, record)
        return WorkspaceSchema(path, version, previous if migrated else None, migrated, False)

    legacy = any(root.glob("projects/*/project.json"))
    if legacy:
        _migrate_v0_to_v1(root)
    _atomic_write(path, _new_record(previous_version=0 if legacy else None, migrated=legacy))
    return WorkspaceSchema(path, SCHEMA_VERSION, 0 if legacy else None, legacy, not legacy)
