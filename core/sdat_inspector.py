"""只检查已观察到的 sdat 结构，不推断 S 参数定义、频率单位或几何含义。"""

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd

from core.parser import decode_text


def inspect_sdat(path):
    """输入原始路径；返回结构记录和未解释的九列表，所有列使用中性名称。

    仅支持已观察到的 Cluster XML + 数值表。它不是电磁/S 参数解析器。
    """
    raw = Path(path).read_bytes()
    text, encoding = decode_text(raw)
    end = text.rfind("</Cluster>")
    if end < 0 or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("未知或不支持的 sdat 元数据结构。")
    end += len("</Cluster>")
    xml_text = text[:end].strip()
    root = ET.fromstring(xml_text)
    if root.tag != "Cluster":
        raise ValueError("未知 sdat 根元素。")
    rows, line_numbers = [], []
    offset = text[:end].count("\n")
    for index, line in enumerate(text[end:].splitlines()):
        if not line.strip():
            continue
        tokens = line.split()
        if len(tokens) != 9:
            raise ValueError(f"sdat 数值段源行 {offset+index+1} 应为 9 列，实际 {len(tokens)}。")
        values = [float(token) for token in tokens]
        if not np.isfinite(values).all():
            raise ValueError("sdat 数值段包含缺失或非有限值。")
        rows.append(values)
        line_numbers.append(offset+index+1)
    if not rows:
        raise ValueError("sdat 数值段为空。")
    columns = [f"column_{i}" for i in range(1, 10)]
    table = pd.DataFrame(rows, columns=columns)
    record = {"status": "structure_only_not_for_calculation", "encoding": encoding,
              "sha256": hashlib.sha256(raw).hexdigest(), "metadata_xml": xml_text,
              "rows": len(table), "columns": columns, "source_rows": line_numbers,
              "field_meanings": "unknown", "frequency_unit": "unknown", "s_parameter_order": "unknown",
              "note": "只保存原始结构；未映射 Frequency/S11/S21，也未计算 R/T/A。"}
    return record, table
