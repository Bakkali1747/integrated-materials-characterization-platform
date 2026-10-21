"""从同目录 S 参数文件的夹具块读取样品厚度与环境；不猜测缺失字段。"""

import hashlib
import math
import xml.etree.ElementTree as ET
from pathlib import Path

from core.parser import decode_text

FIXTURE_KEYS = {"L": "L_mm", "A": "A_mm", "B": "B_mm", "D": "thickness_mm"}
ENVIRONMENT_KEYS = {"温度": "temperature_c"}


def _float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _header_text(path):
    """读取文件开头的 XML 块；遇到第一行数值数据即停止。"""
    text, encoding = decode_text(Path(path).read_bytes())
    lines = []
    for line in text.splitlines():
        if line.lstrip().startswith("<") or not line.strip():
            lines.append(line)
            continue
        break
    if not lines:
        raise ValueError("文件没有 XML 夹具头。")
    return "\n".join(lines), encoding


def read_fixture(path):
    """输入 sdat 路径；返回夹具尺寸、温度、类型及来源哈希。

    只接受明确的 DBL/Name/Val 字段；缺失或非有限值保持为空，不猜测单位。
    """
    path = Path(path)
    header, encoding = _header_text(path)
    root = ET.fromstring(header)
    values = {"encoding": encoding}

    def walk(node, cluster_name=""):
        current = cluster_name
        for child in node:
            if child.tag == "Name" and child.text:
                current = child.text.strip()
        for child in node:
            if child.tag == "DBL":
                name = next((item.text.strip() for item in child if item.tag == "Name" and item.text), "")
                raw = next((item.text.strip() for item in child if item.tag == "Val" and item.text), "")
                key = FIXTURE_KEYS.get(name) or ENVIRONMENT_KEYS.get(name)
                if key:
                    value = _float(raw)
                    if value is not None:
                        values[key] = value
            elif child.tag == "EW":
                name = next((item.text.strip() for item in child if item.tag == "Name" and item.text), "")
                choices = [item.text.strip() for item in child if item.tag == "Choice" and item.text]
                raw = next((item.text.strip() for item in child if item.tag == "Val" and item.text), "")
                if name == "类型" and raw.isdigit() and int(raw) < len(choices):
                    values["fixture_type"] = choices[int(raw)]
            elif child.tag == "Cluster":
                walk(child, current)

    walk(root)
    if values.get("thickness_mm") is not None and values["thickness_mm"] <= 0:
        values.pop("thickness_mm")
    values.update({"source": str(path.resolve()),
                   "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return values


def find_fixture_for_sample(memp_path):
    """输入 .memp；返回同目录同编号 S 参数文件的夹具信息；找不到返回空 dict。"""
    memp_path = Path(memp_path)
    sample_id = memp_path.stem.split("_", 1)[0]
    directory = memp_path.parent
    candidates = {}
    for stem in {memp_path.stem, sample_id}:
        for pattern in (f"{stem}.sdat", f"{stem}_S-parameter*.sdat", f"{stem}_*.sdat"):
            for candidate in directory.glob(pattern):
                if candidate.is_file():
                    candidates[candidate] = candidate.stat().st_mtime
    for candidate in sorted(candidates, key=candidates.get, reverse=True):
        try:
            fixture = read_fixture(candidate)
        except (OSError, ValueError, ET.ParseError):
            continue
        if fixture.get("thickness_mm") is not None:
            return fixture
    return {}


def fixture_for_path(path):
    """按输入类型读取夹具：.sdat 直接读，.memp 找同目录配对文件。"""
    path = Path(path)
    if path.suffix.lower() == ".sdat":
        try:
            return read_fixture(path)
        except (OSError, ValueError, ET.ParseError):
            return {}
    if path.suffix.lower() == ".memp":
        return find_fixture_for_sample(path)
    return {}
