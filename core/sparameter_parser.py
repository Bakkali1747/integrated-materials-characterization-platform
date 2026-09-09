"""已知 sdat 的结构解析与候选语义映射；不使用 ε/μ 的虚部符号转换。"""

from dataclasses import dataclass
from pathlib import Path
import hashlib
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from core.sparameter_mapping import SParameterMapping, S_NAMES


@dataclass
class SParameterData:
    """频率为 GHz；s_parameters 保存真正的复数数组；raw_columns 保留文件九列。"""

    frequency_ghz: np.ndarray
    s_parameters: dict
    raw_columns: pd.DataFrame
    metadata: dict


def decode_sdat(raw, encoding=None):
    """输入字节及可选显式编码；返回严格解码文本与采用的编码，不替换错误字节。

    无 BOM 时优先 GB18030，再尝试 GBK/UTF-8；存在 UTF-8 BOM 时使用明确标识。
    解码成功代表兼容，不宣称自动识别出了唯一原始编码。
    """
    if b"\x00" in raw:
        raise ValueError("sdat 含 NUL 字节；当前仅支持已观察的文本结构。")
    candidates = [encoding] if encoding else (["utf-8-sig"] if raw.startswith(b"\xef\xbb\xbf") else ["gb18030", "gbk", "utf-8-sig"])
    for candidate in candidates:
        try:
            return raw.decode(candidate, errors="strict"), candidate
        except UnicodeDecodeError:
            continue
    raise ValueError("sdat 无法严格解码，请指定已知编码。")


def xml_node_record(node):
    """将 XML 元素转换为普通数据对象，保留层级/属性/文本；不解释几何字段单位。"""
    return {"tag": node.tag, "attributes": dict(node.attrib), "text": (node.text or "").strip(),
            "children": [xml_node_record(child) for child in node]}


def read_sparameters(path, mapping=None, *, encoding=None):
    """输入只读 sdat 路径和 SParameterMapping；返回结构化 SParameterData。

    XML 与 tab 分隔九列分别解析；频率按配置转换 GHz、严格递增且不插值。
    Sij = real + j*imag。这里绝不调用 εr=ε′−jε″ 的构造函数。
    """
    mapping = mapping or SParameterMapping()
    mapping.validate()
    path = Path(path)
    if path.suffix.lower() != ".sdat":
        raise ValueError("此解析器仅接受 .sdat。")
    raw = path.read_bytes()
    text, used_encoding = decode_sdat(raw, encoding)
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("不支持含 DOCTYPE/ENTITY 的 sdat header。")
    end = text.rfind("</Cluster>")
    if end < 0:
        raise ValueError("缺少完整的 Cluster metadata header。")
    end += len("</Cluster>")
    xml_text = text[:end].strip()
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        raise ValueError(f"metadata XML 不完整或格式错误：{error}") from error
    if root.tag != "Cluster":
        raise ValueError("未知 metadata 根元素。")
    lines = text[end:].splitlines()
    offset = len(text[:end].splitlines()) - 1
    rows, source_rows = [], []
    started, blank_after_data = False, False
    for index, line in enumerate(lines):
        source_row = offset+index+1
        if not line.strip():
            if started:
                blank_after_data = True
            continue
        if blank_after_data:
            raise ValueError(f"sdat 源行 {source_row} 前有数据区内部空行，未自动跳过。")
        started = True
        tokens = line.split("\t")
        if len(tokens) != 9:
            raise ValueError(f"sdat 源行 {source_row} 必须为 tab 分隔的 9 列，实际 {len(tokens)}。")
        values = []
        for column, token in enumerate(tokens):
            try:
                value = float(token.strip())
            except ValueError:
                raise ValueError(f"sdat 源行 {source_row} column {column} 缺失或非数值。") from None
            if not np.isfinite(value):
                raise ValueError(f"sdat 源行 {source_row} column {column} 为 NaN/无限值。")
            values.append(value)
        rows.append(values)
        source_rows.append(source_row)
    if not rows:
        raise ValueError("sdat 数据区为空。")
    array = np.asarray(rows, dtype=float)
    factors = {"Hz": 1e-9, "kHz": 1e-6, "MHz": 1e-3, "GHz": 1.}
    frequency = array[:, mapping.frequency_column] * factors[mapping.frequency_unit]
    if not np.isfinite(frequency).all() or np.any(frequency <= 0) or np.any(np.diff(frequency) <= 0):
        raise ValueError("Frequency 必须有限、正值且严格递增；不排序或合并重复点。")
    if mapping.expected_points is not None and len(frequency) != mapping.expected_points:
        raise ValueError(f"预期 {mapping.expected_points} 点，实际 {len(frequency)} 点，文件可能不完整。")
    for actual, expected, description in ((frequency[0], mapping.expected_frequency_start_ghz, "起点"),
                                           (frequency[-1], mapping.expected_frequency_stop_ghz, "终点")):
        if expected is not None and not np.isclose(actual, expected, rtol=0, atol=mapping.frequency_grid_atol_ghz):
            raise ValueError(f"Frequency {description}与 schema 预期不一致。")
    if mapping.expected_frequency_step_ghz is not None and not np.allclose(np.diff(frequency), mapping.expected_frequency_step_ghz, rtol=0, atol=mapping.frequency_grid_atol_ghz):
        raise ValueError("Frequency 步长与 schema 预期不一致；未重采样。")
    parameters = {}
    for name in S_NAMES:
        real, imag = mapping.complex_columns[name]
        parameters[name] = array[:, real] + 1j*array[:, imag]
    metadata = {"raw_file": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "file_size_bytes": len(raw),
                "encoding_used": used_encoding, "metadata_xml": xml_text, "metadata_tree": xml_node_record(root),
                "source_rows": source_rows, "schema": mapping.to_dict(), "schema_status": mapping.schema_status,
                "mapping_origin": "user-provided candidate; manufacturer order not confirmed",
                "complex_convention": "Sij = real + j*imag", "interpolation": "OFF"}
    return SParameterData(frequency, parameters, pd.DataFrame(array, columns=[f"column_{i}" for i in range(9)]), metadata)
