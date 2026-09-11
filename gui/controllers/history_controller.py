"""只读历史产物，不导入任何计算入口。"""
from pathlib import Path
import hashlib
import json
from gui.controllers.analysis_controller import Cancelled

RECORDS = {"analysis_record.json", "batch_record.json", "comparison_record.json"}


def discover_history(folder, progress, cancelled):
    paths = []
    for path in Path(folder).rglob("*.json"):
        if cancelled():
            raise Cancelled("历史扫描已取消")
        if path.name in RECORDS and path.resolve().is_relative_to(Path(folder).resolve()):
            paths.append(path)
    progress(100, f"找到 {len(paths)} 份运行记录")
    return sorted(paths, reverse=True)


def contained(directory, name):
    candidate = directory / name
    if Path(name).is_absolute() or not candidate.resolve().is_relative_to(directory.resolve()):
        raise ValueError(f"历史产物路径越界：{name}")
    return candidate


def load_history(path, progress, cancelled):
    path = Path(path)
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("运行记录必须是 JSON 对象。")
    directory = path.parent
    checks = []
    hashes = record.get("artifacts_sha256", {})
    for i, (name, digest) in enumerate(hashes.items()):
        if cancelled():
            raise Cancelled("历史读取已取消")
        artifact = contained(directory, name)
        state = "MISSING" if not artifact.is_file() else "PASS" if hashlib.sha256(artifact.read_bytes()).hexdigest() == digest else "CHANGED"
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
    return dict(directory=directory, record=record, checks=checks, figures=figures, summaries=summaries, preview=preview)


def read_figure(directory, path, cancelled):
    if cancelled():
        raise Cancelled("图片读取已取消")
    return contained(Path(directory), str(Path(path).relative_to(directory))).read_bytes()
