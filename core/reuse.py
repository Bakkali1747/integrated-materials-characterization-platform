"""按源文件哈希与数值配置复用已完成的单样品运行。"""

import hashlib
import json
from pathlib import Path

CONFIG_KEYS = ("requested_frequency_range_ghz", "requested_thickness_range_mm", "thickness_step_mm",
               "curve_thickness_mm", "rl_threshold_db", "eab_threshold_crossing", "parser_options",
               "quarter_wave_orders", "impedance_tolerance")

# 只在解析、RL/EAB 或相关数值语义变化时递增。显示和导出变化不应让缓存失效。
ANALYSIS_CACHE_VERSION = 1


def sha256_file(path):
    """分块计算文件 SHA-256；不把大文件整体读入内存。"""
    value = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def configuration_key(configuration):
    """只比较影响数值结果的字段；图幅、DPI、入口等不参与。"""
    subset = {key: configuration.get(key) for key in CONFIG_KEYS}
    return json.dumps(subset, sort_keys=True, ensure_ascii=False, default=str)


def run_key(sample, raw_sha256, configuration, cache_version=ANALYSIS_CACHE_VERSION):
    """生成复用键；引擎版本变化时同一源文件和配置也必须重新计算。"""
    return str(sample), str(raw_sha256), int(cache_version), configuration_key(configuration or {})


def index_completed_runs(root):
    """扫描输出根目录，返回 key -> 运行目录；只收录当前引擎生成的成功记录。"""
    index = {}
    root = Path(root).resolve()
    if not root.is_dir():
        return index
    for record_path in root.rglob("analysis_record.json"):
        if any(part.endswith(".data") or part == "_archive" for part in record_path.parts):
            continue
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict) or record.get("status") != "success":
            continue
        raw_sha = record.get("raw_sha256")
        if not raw_sha or raw_sha == "unavailable":
            continue
        cache_version = record.get("analysis_cache_version")
        if cache_version != ANALYSIS_CACHE_VERSION:
            continue
        key = run_key(record.get("sample"), raw_sha, record.get("configuration", {}), cache_version)
        index.setdefault(key, record_path.parent)
    return index
