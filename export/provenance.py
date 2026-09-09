"""每次运行的可追溯记录；失败也留下记录，不覆盖历史运行。"""

from datetime import datetime
from importlib.metadata import version
from pathlib import Path
import hashlib
import json
import math
import platform
import re
import subprocess
import uuid
from core import __version__


def json_safe(value):
    """输入嵌套结果；将非有限浮点转为显式字符串，输出符合标准 JSON 的对象。"""
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def git_state():
    """读取项目 Git 提交及工作区状态；Git 不可用时明确返回 unavailable。"""
    root = Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, stderr=subprocess.DEVNULL, text=True).strip()
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, stderr=subprocess.DEVNULL, text=True)
        return {"commit": commit, "dirty": bool(status.strip())}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": "unavailable", "dirty": "unavailable"}


def new_run(output_root, sample_name, raw_path, configuration):
    """输入输出根目录、样品名、原始路径和配置；返回唯一运行目录及初始记录。"""
    now = datetime.now().astimezone()
    run_id = now.strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:12]
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", sample_name).strip(" .") or "sample"
    # 固定前缀避免 Windows CON/NUL 等保留名称，限制长度避免超长路径。
    safe_name = "sample_" + safe_name[:80]
    directory = Path(output_root) / safe_name / run_id
    directory.mkdir(parents=True, exist_ok=False)
    state = git_state()
    record = {"sample": sample_name, "analysis_date": now.isoformat(timespec="seconds"),
              "run_id": run_id, "software_version": __version__, "git": state,
              "build_state": "modified" if state["dirty"] is True else "clean" if state["dirty"] is False else "unavailable",
              "raw_file": str(Path(raw_path).resolve()), "configuration": configuration,
              "missing_data_interpolation": "OFF", "complex_convention": "ε'-jε'', μ'-jμ''",
              "time_convention": "exp(+jωt)", "status": "started",
              "commercial_reference_validation": "pending",
              "python_version": platform.python_version(),
              "dependencies": {p: version(p) for p in ("numpy", "pandas", "matplotlib", "openpyxl")}}
    try:
        record["raw_sha256"] = hashlib.sha256(Path(raw_path).read_bytes()).hexdigest()
    except OSError as error:
        record["raw_sha256"] = "unavailable"
        record["source_read_error"] = str(error)
    write_record(directory, record)
    return directory, record


def write_record(directory, record):
    """输入运行目录和记录；写出机器可读 JSON 及相同内容的可读 TXT。"""
    text = json.dumps(json_safe(record), ensure_ascii=False, indent=2, allow_nan=False)
    for filename in ("analysis_record.json", "analysis_record.txt"):
        (Path(directory) / filename).write_text(text + "\n", encoding="utf-8")


def artifact_hashes(directory):
    """输入运行目录；返回结果文件哈希，不包含仍需更新的记录自身。"""
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in Path(directory).rglob("*") if path.is_file() and not path.name.startswith("analysis_record.")}
