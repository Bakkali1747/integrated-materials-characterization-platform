"""生成可分享的运行记录副本：去掉绝对路径，保留哈希、验证状态与摘要。"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

RECORDS = ("analysis_record.json", "batch_record.json", "comparison_record.json", "reference_record.json")
SUMMARIES = ("summary.json", "summary.csv", "sources.csv", "data_quality.json", "validation_errors.json")
PATH_KEYS = {"raw_file", "source_run", "run_directory", "theory_run", "measured_run",
             "reference_file", "schema_file", "output", "path"}


def looks_absolute(text):
    return bool(re.match(r"^[A-Za-z]:[\\/]", text) or text.startswith("\\\\") or text.startswith("/"))


def redact(value, key=None):
    """递归替换绝对路径为文件名；不猜测非路径字符串的含义。"""
    if isinstance(value, dict):
        return {name: redact(item, name) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item, key) for item in value]
    if isinstance(value, str) and (key in PATH_KEYS or looks_absolute(value)):
        name = Path(value.replace("\\", "/")).name
        return name or "<redacted>"
    return value


def _sha256(path):
    value = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _redact_csv(source, target):
    """逐单元格脱敏 CSV，保留原有文本格式与数值精度。"""
    import csv
    with source.open("r", encoding="utf-8-sig", newline="") as input_handle:
        rows = list(csv.reader(input_handle))
    with target.open("w", encoding="utf-8-sig", newline="") as output_handle:
        writer = csv.writer(output_handle)
        for row in rows:
            writer.writerow([Path(cell.replace("\\", "/")).name
                             if isinstance(cell, str) and looks_absolute(cell) else cell
                             for cell in row])


def export_shareable(run_directory, output_directory):
    """输入运行目录与目标目录；写出脱敏记录、摘要和说明，不改动原分析。"""
    run = Path(run_directory).resolve()
    output = Path(output_directory).resolve()
    record_path = next((run / name for name in RECORDS if (run / name).is_file()), None)
    if record_path is None:
        raise ValueError("所选目录没有可分享的运行记录。")
    if output == run or output.is_relative_to(run):
        raise ValueError("分享目录不能位于原运行目录内。")
    if output.exists() and any(output.iterdir()):
        raise ValueError("分享目录必须不存在或为空，避免覆盖已有文件。")
    output.mkdir(parents=True, exist_ok=True)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("运行记录必须是 JSON 对象。")
    redacted = redact(record)
    files = {}
    target = output / record_path.name
    target.write_text(json.dumps(redacted, ensure_ascii=False, indent=2), encoding="utf-8")
    files[target.name] = _sha256(target)
    for name in SUMMARIES:
        source = run / name
        if not source.is_file():
            continue
        if source.suffix.lower() == ".csv":
            _redact_csv(source, output / name)
        elif source.suffix.lower() == ".json":
            try:
                payload = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                (output / name).write_bytes(source.read_bytes())
            else:
                (output / name).write_text(json.dumps(redact(payload), ensure_ascii=False, indent=2),
                                           encoding="utf-8")
        else:
            (output / name).write_bytes(source.read_bytes())
        files[name] = _sha256(output / name)
    status = record.get("status", "unknown")
    validation = record.get("validation_status") or record.get("schema_status") or "unknown"
    raw_sha = record.get("raw_sha256", "unavailable")
    lines = [
        "可分享运行记录（由综合材料表征分析平台生成）",
        f"原始运行目录名：{run.name}",
        f"运行状态：{status}",
        f"验证状态：{validation}",
        f"源文件 SHA-256：{raw_sha}",
        "已移除本地绝对路径，仅保留文件名；哈希与数值内容未修改。",
        "图片默认不包含在分享包内；如需图片，请单独导出并核对 provenance。",
        "该副本不改变原分析的结论；外部验证状态仍以原记录为准。",
    ]
    (output / "README_SHARE.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "share_manifest.json").write_text(json.dumps(
        {"source_run": run.name, "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
         "files": files}, ensure_ascii=False, indent=2), encoding="utf-8")
    return output
