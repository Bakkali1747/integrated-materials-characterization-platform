"""输出目录体积治理：只移动、不直接删除；任何动作都可以先预演。"""

import json
import os
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from core.reuse import configuration_key

ARCHIVE_NAME = "_archive"
SKIP_PARTS = {ARCHIVE_NAME, "figures", ".git", ".venv"}


def _record_json(directory):
    return directory / "analysis_record.json"


def scan_runs(root):
    """输入输出根目录；返回每个运行目录的状态、日期与占用空间。

    只识别含 analysis_record.json 的运行目录；跳过 .data、figures 与归档区，
    不读取大矩阵，只做文件大小统计。
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"输出目录不存在：{root}")
    runs = []
    for record in sorted(root.rglob("analysis_record.json")):
        directory = record.parent
        relative = directory.relative_to(root)
        if any(part in SKIP_PARTS or part.endswith(".data") for part in relative.parts):
            continue
        try:
            info = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {}
        if not isinstance(info, dict):
            info = {}
        size = 0
        try:
            for path in directory.rglob("*"):
                try:
                    if path.is_file():
                        size += path.stat().st_size
                except OSError:
                    continue
        except OSError:
            pass
        runs.append({"directory": directory, "relative": relative.as_posix(),
                     "sample": info.get("sample"), "run_id": info.get("run_id"),
                     "status": info.get("status", "unknown"), "analysis_date": info.get("analysis_date"),
                     "raw_sha256": info.get("raw_sha256"),
                     "analysis_cache_version": info.get("analysis_cache_version"),
                     "configuration_key": configuration_key(info.get("configuration", {})),
                     "size_bytes": size})
    return runs


def find_duplicates(runs):
    """按样品、源哈希和数值配置分组；每组保留最新一份，其余可回收。"""
    groups = defaultdict(list)
    for run in runs:
        raw = run.get("raw_sha256")
        if not raw or raw == "unavailable":
            continue
        groups[(run.get("sample"), raw, run.get("analysis_cache_version"),
                run.get("configuration_key"))].append(run)
    duplicates = []
    for (sample, raw, cache_version, config), items in groups.items():
        if len(items) < 2:
            continue
        ordered = sorted(items, key=lambda item: str(item.get("analysis_date") or ""), reverse=True)
        duplicates.append({"sample": sample, "raw_sha256": raw,
                           "analysis_cache_version": cache_version, "configuration_key": config,
                           "count": len(ordered), "keep": ordered[0]["relative"],
                           "runs": [item["relative"] for item in ordered[1:]],
                           "reclaimable_bytes": sum(int(item.get("size_bytes", 0)) for item in ordered[1:])})
    return sorted(duplicates, key=lambda group: group["reclaimable_bytes"], reverse=True)


def select_runs(runs, older_than_days=None, sample=None, status=None):
    """按日期/样品/状态筛选；缺少分析日期的运行不会进入“按日期归档”。"""
    now = datetime.now(timezone.utc)
    selected = []
    for run in runs:
        if sample and sample.casefold() not in str(run.get("sample") or "").casefold():
            continue
        if status and run.get("status") != status:
            continue
        if older_than_days is not None:
            try:
                date = datetime.fromisoformat(str(run.get("analysis_date")))
            except (TypeError, ValueError):
                continue
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            if (now - date).total_seconds() < float(older_than_days) * 86400:
                continue
        selected.append(run)
    return selected


def _recycle_path(path):
    """把目录移入 Windows 回收站；其他平台或失败时抛 OSError，绝不永久删除。"""
    if os.name != "nt":
        raise OSError("当前平台不支持回收站删除；请使用归档。")
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", wintypes.WORD),
                    ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", wintypes.LPCWSTR)]

    FO_DELETE = 3
    FOF_ALLOWUNDO, FOF_NOCONFIRMATION, FOF_SILENT, FOF_NOERRORUI = 0x40, 0x10, 0x4, 0x400
    operation = SHFILEOPSTRUCTW(None, FO_DELETE, str(Path(path).resolve()) + "\0\0", None,
                                FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI,
                                False, None, None)
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted:
        raise OSError(f"移入回收站失败（代码 {result}）。")


def delete_runs(runs, root, apply=False, recycler=None):
    """把选中的运行目录移入回收站；默认只预演，不永久删除。

    recycler 便于测试注入；生产环境使用 Windows SHFileOperation(FOF_ALLOWUNDO)。
    """
    root = Path(root).resolve()
    recycler = recycler or _recycle_path
    planned = []
    for run in runs:
        source = (root / run["relative"]).resolve()
        if not _record_json(source).is_file():
            raise ValueError(f"不是有效运行目录：{source}")
        if source == root or not source.is_relative_to(root):
            raise ValueError(f"运行目录越界：{source}")
        planned.append({"source": source, "relative": run["relative"],
                        "size_bytes": int(run.get("size_bytes", 0)),
                        "sample": run.get("sample"), "status": run.get("status")})
    total = sum(item["size_bytes"] for item in planned)
    report = {"status": "planned" if not apply else "deleted", "root": str(root),
              "total_bytes": total, "runs": [{key: (str(value) if isinstance(value, Path) else value)
                                              for key, value in item.items()} for item in planned]}
    if not apply:
        return report
    deleted, failures = [], []
    for item in planned:
        try:
            recycler(item["source"])
        except OSError as error:
            failures.append({"relative": item["relative"], "error": f"{type(error).__name__}: {error}"})
            continue
        deleted.append({"relative": item["relative"], "size_bytes": item["size_bytes"],
                        "sample": item["sample"], "status": item["status"]})
        parent = item["source"].parent
        while parent != root and parent.is_relative_to(root):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    manifest_path = root / "deletion_manifest.json"
    manifest = {"deletions": []}
    if manifest_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and isinstance(existing.get("deletions"), list):
                manifest = existing
        except (OSError, ValueError):
            pass
    manifest["deletions"].append({"deleted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                                  "runs": deleted, "failures": failures})
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    report["status"] = "deleted" if not failures else "partial"
    report["runs"] = deleted
    report["failures"] = failures
    return report


def archive_runs(runs, root, archive_root=None, apply=False):
    """把选中的运行目录移动到归档区，保留相对路径并追加清单。

    apply=False 只返回将移动的内容；apply=True 才执行。拒绝把归档区放进
    任一被移动的运行目录，遇到同名目标时追加时间戳，不覆盖旧归档。
    """
    root = Path(root).resolve()
    archive_root = Path(archive_root).resolve() if archive_root else root / ARCHIVE_NAME
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
    planned = []
    for run in runs:
        source = (root / run["relative"]).resolve()
        if not _record_json(source).is_file():
            raise ValueError(f"不是有效运行目录：{source}")
        if archive_root == source or archive_root.is_relative_to(source):
            raise ValueError("归档目录不能位于待归档的运行目录内。")
        target = archive_root / run["relative"]
        if target.exists():
            target = target.with_name(target.name + "_" + timestamp)
        planned.append({"source": source, "target": target, "relative": run["relative"],
                        "size_bytes": int(run.get("size_bytes", 0)),
                        "sample": run.get("sample"), "status": run.get("status")})
    total = sum(item["size_bytes"] for item in planned)
    report = {"status": "planned" if not apply else "archived", "root": str(root),
              "archive_root": str(archive_root), "total_bytes": total,
              "runs": [{key: (str(value) if isinstance(value, Path) else value)
                        for key, value in item.items()} for item in planned]}
    if not apply:
        return report
    archive_root.mkdir(parents=True, exist_ok=True)
    moved, failures = [], []
    for item in planned:
        try:
            item["target"].parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item["source"]), str(item["target"]))
        except OSError as error:
            failures.append({"relative": item["relative"], "error": f"{type(error).__name__}: {error}"})
            continue
        moved.append({"relative": item["relative"], "archived_to": str(item["target"]),
                      "size_bytes": item["size_bytes"], "sample": item["sample"], "status": item["status"]})
        parent = item["source"].parent
        while parent != root and parent.is_relative_to(root):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    manifest_path = archive_root / "archive_manifest.json"
    manifest = {"archives": []}
    if manifest_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and isinstance(existing.get("archives"), list):
                manifest = existing
        except (OSError, ValueError):
            pass
    manifest["archives"].append({"archived_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                                 "root": str(root), "runs": moved, "failures": failures})
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    report["status"] = "archived" if not failures else "partial"
    report["runs"] = moved
    report["failures"] = failures
    return report
