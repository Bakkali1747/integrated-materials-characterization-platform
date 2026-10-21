"""可视化映射的文件预览；正式分析仍由 core.parser 验证。"""
from pathlib import Path

import pandas as pd

from core.models import COLUMNS
from core.parser import decode_text, read_csv_table


def preview_table(path):
    """只读取表头与少量数据行用于映射预览，不把大文件整体载入内存。"""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        # 按二进制完整行读取，避免在多字节字符中间截断；只取预览所需行数。
        with path.open("rb") as handle:
            raw = b"".join(handle.readlines()[:12])
        text, _ = decode_text(raw)
        table, _ = read_csv_table(text, ",")
    elif suffix in {".xls", ".xlsx"}:
        table = pd.read_excel(path, header=None, nrows=7,
                              engine="xlrd" if suffix==".xls" else "openpyxl")
        if table.empty:
            raise ValueError("Excel 工作表为空。")
        table.columns = table.iloc[0].tolist()
        table = table.iloc[1:]
    else:
        raise ValueError("映射预览只适用于 CSV / Excel；MEMP、SDAT 使用各自解析器。")
    if not all(isinstance(c,str) and c.strip() for c in table.columns) or len(set(table.columns))!=len(table.columns):
        raise ValueError("预览要求首行是非空、不重复的文本列名；若首行是报告标题，"
                         "请在左侧设置“Excel 工作表 / 表头行”后重新选择示例文件。")
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
