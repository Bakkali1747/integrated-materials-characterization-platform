"""每次运行的可追溯记录；失败也留下记录，不覆盖历史运行。"""

import hashlib
import json
import math
import platform
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import numpy as np

from core import __version__
from core.reuse import ANALYSIS_CACHE_VERSION


def json_safe(value):
    """输入嵌套结果；将非有限浮点转为显式字符串，输出符合标准 JSON 的对象。"""
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def _git_executable():
    """优先 PATH；Windows 安装后当前进程 PATH 未刷新时回退到常见安装位置。"""
    found = shutil.which("git")
    if found:
        return found
    candidates = (r"C:\Program Files\Git\cmd\git.exe",
                  r"C:\Program Files (x86)\Git\cmd\git.exe",
                  str(Path.home() / "AppData/Local/Programs/Git/cmd/git.exe"))
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    return "git"


def git_state():
    """读取项目 Git 提交及工作区状态；Git 不可用时明确返回 unavailable。"""
    if getattr(sys, "frozen", False):
        from application_paths import resource_root
        try:
            info = json.loads((resource_root() / "build_info.json").read_text(encoding="utf-8"))
            return {"commit": info["commit"], "dirty": info["dirty"], "origin": "packaged_build"}
        except (OSError, ValueError, KeyError):
            return {"commit": "unavailable", "dirty": "unavailable", "origin": "packaged_build"}
    root = Path(__file__).resolve().parents[1]
    git = _git_executable()
    try:
        commit = subprocess.check_output([git, "rev-parse", "HEAD"], cwd=root, stderr=subprocess.DEVNULL, text=True).strip()
        status = subprocess.check_output([git, "status", "--porcelain"], cwd=root, stderr=subprocess.DEVNULL, text=True)
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
              "analysis_cache_version": ANALYSIS_CACHE_VERSION,
              "build_state": "modified" if state["dirty"] is True else "clean" if state["dirty"] is False else "unavailable",
              "raw_file": str(Path(raw_path).resolve()), "configuration": configuration,
              "missing_data_interpolation": "OFF", "complex_convention": "ε'-jε'', μ'-jμ''",
              "time_convention": "exp(+jωt)", "status": "started",
              "commercial_reference_validation": "pending",
              "python_version": platform.python_version(),
              "dependencies": {p: version(p) for p in ("numpy", "pandas", "matplotlib", "openpyxl")}}
    try:
        hasher = hashlib.sha256()
        with open(raw_path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(block)
        record["raw_sha256"] = hasher.hexdigest()
    except OSError as error:
        record["raw_sha256"] = "unavailable"
        record["source_read_error"] = str(error)
    write_record(directory, record)
    return directory, record


def figure_provenance(record=None, *, dpi=None, extra=None):
    """输入分析记录（可缺省）；返回写入图片配套数据的来源说明。

    独立导出没有分析上下文时 validation_status 明确写 unknown，不冒充已验证。
    """
    value = {"software_version": __version__, "run_id": None, "sample": None,
             "raw_sha256": None, "configuration_sha256": None,
             "validation_status": "unknown", "dpi": dpi,
             "created_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    if record:
        configuration = record.get("configuration", {})
        value.update({
            "software_version": record.get("software_version", __version__),
            "run_id": record.get("run_id"),
            "sample": record.get("sample"),
            "raw_sha256": record.get("raw_sha256"),
            "validation_status": record.get("validation_status", "unknown"),
            "configuration_sha256": hashlib.sha256(
                json.dumps(configuration, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest(),
            "analysis_date": record.get("analysis_date"),
        })
    if extra:
        value.update(extra)
    return json_safe(value)


def write_record(directory, record):
    """输入运行目录和记录；写出机器可读 JSON 及相同内容的可读 TXT。"""
    text = json.dumps(json_safe(record), ensure_ascii=False, indent=2, allow_nan=False)
    (Path(directory) / "analysis_record.json").write_text(text + "\n", encoding="utf-8")
    fields = {"Sample": record["sample"], "Analysis date": record["analysis_date"],
              "Software version": record["software_version"], "Build state": record["build_state"],
              "Analysis cache version": record.get("analysis_cache_version", "unavailable"),
              "Git commit": record["git"]["commit"], "Raw file": record["raw_file"],
              "Raw SHA-256": record.get("raw_sha256", "unavailable"),
              "Frequency range (GHz)": record.get("frequency_range_ghz", "unavailable"),
              "Thickness range (mm)": record.get("thickness_range_mm", "unavailable"),
              "Thickness step (mm)": record["configuration"]["thickness_step_mm"],
              "RL threshold (dB)": record["configuration"]["rl_threshold_db"],
              "Missing-data interpolation": record["missing_data_interpolation"],
              "EAB threshold crossing": record["configuration"].get("eab_threshold_crossing", "unavailable"),
              "Complex convention": record["complex_convention"],
              "Validation": record.get("validation_status", "pending"), "Status": record["status"]}
    header = "\n".join(f"{key}: {value}" for key, value in fields.items())
    (Path(directory) / "analysis_record.txt").write_text(header + "\n\nComplete record:\n" + text + "\n", encoding="utf-8")


def artifact_hashes(directory):
    """输入运行目录；返回结果文件哈希，不包含仍需更新的记录自身。"""
    def digest(path, chunk=1024 * 1024):
        value = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(chunk), b""):
                value.update(block)
        return value.hexdigest()
    return {str(path.relative_to(directory)): digest(path)
            for path in Path(directory).rglob("*") if path.is_file() and not path.name.startswith("analysis_record.")}
