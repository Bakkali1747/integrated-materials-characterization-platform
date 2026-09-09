"""批次输入发现和清单校验；物理计算复用单样品流程。"""

from pathlib import Path
import json

PARSER_KEYS = {"frequency_unit", "imaginary_convention", "convention_confirmed", "column_map", "sheet", "encoding", "delimiter"}
ANALYSIS_KEYS = {"frequency_min", "frequency_max", "thickness_min", "thickness_max", "thickness_step",
                 "curve_thickness", "threshold", "eab_crossing", "quarter_wave_orders", "impedance_tolerance"}


def validate_entries(entries):
    """输入清单条目；拒绝空批次、重名与未知解析字段，保持样品一一可追溯。"""
    if not entries:
        raise ValueError("没有待分析样品。")
    names = []
    for entry in entries:
        if not isinstance(entry.get("name"), str) or not entry["name"].strip():
            raise ValueError("每个样品必须有非空名称。")
        if set(entry.get("parser", {})) - PARSER_KEYS:
            raise ValueError(f"{entry['name']} 有未知 parser 配置。")
        names.append(entry["name"])
    if len(set(names)) != len(names):
        raise ValueError("样品名称重复，请用清单指定唯一名称。")


def discover_samples(directory, parser_options, excluded_roots=()):
    """输入 Raw_Data 目录及显式解析配置；递归发现文件，不修改源文件。

    sdat 也列入批次，但分析将明确失败并输出结构诊断，不偷偷略过。
    """
    root = Path(directory).resolve()
    if not root.is_dir():
        raise ValueError("批量输入必须是存在的目录。")
    excluded = [Path(path).resolve() for path in excluded_roots]
    entries, skipped = [], []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if path.is_symlink() or any(part in (".git", ".venv", ".mplconfig") for part in relative.parts):
            continue
        if any(path.resolve().is_relative_to(item) for item in excluded):
            continue
        if path.name.startswith("~$") or path.suffix.lower() not in (".csv", ".xlsx", ".memp", ".sdat"):
            skipped.append(str(relative))
            continue
        entries.append({"name": relative.with_suffix("").as_posix(), "path": str(path), "parser": dict(parser_options)})
    validate_entries(entries)
    return entries, skipped


def load_manifest(path):
    """输入 JSON 清单；返回显式条目、公共分析配置与比较选择。

    相对文件路径相对于清单所在目录，单样品 parser 覆盖 parser_defaults。
    """
    path = Path(path).resolve()
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if set(payload) - {"samples", "parser_defaults", "analysis", "compare_samples"}:
        raise ValueError("批次清单包含未知顶层字段。")
    defaults = payload.get("parser_defaults", {})
    if set(defaults) - PARSER_KEYS or set(payload.get("analysis", {})) - ANALYSIS_KEYS:
        raise ValueError("批次清单包含未知配置。")
    entries = []
    for item in payload.get("samples", []):
        if set(item) - {"name", "path", "parser"} or "path" not in item:
            raise ValueError("样品条目仅支持 name、path、parser，且必须有 path。")
        source = Path(item["path"])
        if not source.is_absolute():
            source = path.parent / source
        entries.append({"name": item.get("name", source.stem), "path": str(source.resolve()),
                        "parser": {**defaults, **item.get("parser", {})}})
    validate_entries(entries)
    selected = payload.get("compare_samples")
    if selected is not None and (not selected or len(set(selected)) != len(selected) or set(selected)-{e["name"] for e in entries}):
        raise ValueError("compare_samples 必须列出非空、不重复且存在的样品名称。")
    return entries, payload.get("analysis", {}), selected
