"""可视化映射的文件预览；正式分析仍由 core.parser 验证。"""
from pathlib import Path
from io import BytesIO
import json
import pandas as pd
from core.parser import decode_text, read_csv_table
from core.models import COLUMNS


def preview_table(path):
    path = Path(path)
    raw = path.read_bytes()
    if path.suffix.lower() == ".csv":
        text, _ = decode_text(raw)
        table, _ = read_csv_table(text, ",")
    elif path.suffix.lower() in {".xls", ".xlsx"}:
        table = pd.read_excel(BytesIO(raw), header=None, nrows=7,
                              engine="xlrd" if path.suffix.lower()==".xls" else "openpyxl")
        if table.empty:
            raise ValueError("Excel 工作表为空。")
        table.columns = table.iloc[0].tolist()
        table = table.iloc[1:]
    else:
        raise ValueError("映射预览只适用于 CSV / Excel；MEMP、SDAT 使用各自解析器。")
    if not all(isinstance(c,str) and c.strip() for c in table.columns) or len(set(table.columns))!=len(table.columns):
        raise ValueError("预览要求非空且不重复的文本列名。")
    return table.head(6).fillna("")


def validate_template(value):
    if not isinstance(value,dict) or set(value)!={"column_map","frequency_unit","imaginary_convention"}:
        raise ValueError("导入模板字段不正确。")
    mapping = value["column_map"]
    if not isinstance(mapping,dict) or set(mapping)!=set(COLUMNS) or not all(isinstance(v,str) and v for v in mapping.values()) or len(set(mapping.values()))!=5:
        raise ValueError("五个内部字段必须对应五个不同源列。")
    if value["frequency_unit"] not in {"Hz","kHz","MHz","GHz"} or value["imaginary_convention"] not in {"loss","signed"}:
        raise ValueError("单位或虚部解释无效。")
    return value
