"""只读历史产物，不导入任何计算入口。"""
import hashlib
import json
import os
from pathlib import Path

from gui.controllers.analysis_controller import Cancelled

RECORDS = {"analysis_record.json", "batch_record.json", "comparison_record.json", "reference_record.json"}


def discover_history(folder, progress, cancelled):
    paths = []
    root=Path(folder).resolve()
    for current, directories, files in os.walk(root, followlinks=False):
        if cancelled():
            raise Cancelled("历史扫描已取消")
        directories[:]=[d for d in directories if not d.endswith(".data") and not d.startswith(".f-") and d not in {".git",".venv","_archive"}]
        for name in RECORDS.intersection(files):
            path=Path(current)/name
            if path.resolve().is_relative_to(root): paths.append(path)
    progress(100, f"找到 {len(paths)} 份运行记录")
    return sorted(paths, reverse=True)


def history_index(folder, progress, cancelled):
    entries=[]
    for path in discover_history(folder,progress,cancelled):
        if cancelled(): raise Cancelled("历史索引已取消")
        try:
            record=json.loads(path.read_text(encoding="utf-8"))
            label=f"{record.get('sample','批量/比较/对照')} | {record.get('analysis_date','')} | {record.get('status','unknown')}"
            search=label+" "+json.dumps(record.get("configuration",{}),ensure_ascii=False)+" "+str(path.parent)
            entries.append(dict(path=path,label=label,search=search,status=record.get("status","unknown")))
        except (ValueError,OSError,AttributeError):
            entries.append(dict(path=path,label=f"记录读取失败 | {path.parent}",search=str(path),status="invalid"))
    return entries


def contained(directory, name):
    candidate = directory / name
    if Path(name).is_absolute() or not candidate.resolve().is_relative_to(directory.resolve()):
        raise ValueError(f"历史产物路径越界：{name}")
    return candidate


def load_history(path, progress, cancelled, verify=True):
    path = Path(path)
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("运行记录必须是 JSON 对象。")
    directory = path.parent
    checks = []
    hashes = record.get("artifacts_sha256", {})
    for i, (name, digest) in enumerate(hashes.items() if verify else []):
        if cancelled():
            raise Cancelled("历史读取已取消")
        artifact = contained(directory, name)
        state="MISSING"
        if artifact.is_file():
            hasher=hashlib.sha256()
            with artifact.open("rb") as handle:
                while block := handle.read(1024*1024):
                    if cancelled(): raise Cancelled("历史核验已取消")
                    hasher.update(block)
            state="PASS" if hasher.hexdigest()==digest else "CHANGED"
        checks.append((name, state))
        progress(int((i+1)*90/max(len(hashes), 1)), f"核对 {name}")
    figures = [p for p in directory.rglob("*.png") if p.resolve().is_relative_to(directory.resolve())]
    summaries = {}
    for name in ("summary.json", "summary.csv", "sources.csv"):
        candidate = contained(directory, name)
        if candidate.is_file():
            summaries[name] = candidate.read_text(encoding="utf-8-sig")
    figures = sorted(figures)
    preview = read_figure(directory, figures[0], cancelled) if figures else None
    progress(100, "历史读取完成；未重新计算")
    return dict(directory=directory, record=record, checks=checks, figures=figures, summaries=summaries, preview=preview,
                integrity_checked=verify, record_path=path)


def read_figure(directory, path, cancelled):
    if cancelled():
        raise Cancelled("图片读取已取消")
    return contained(Path(directory), str(Path(path).relative_to(directory))).read_bytes()
