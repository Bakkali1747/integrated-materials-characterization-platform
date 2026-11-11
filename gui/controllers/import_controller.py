"""可视化映射的文件预览；正式分析仍由 core.parser 验证。"""
from numbers import Integral
from pathlib import Path

import pandas as pd

from core.models import COLUMNS
from core.parser import decode_text, read_csv_table


def preview_table(path, *, sheet=0, header_row=0):
    """按正式解析所选工作表和表头行读取少量预览数据。"""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        # 按二进制完整行读取，避免在多字节字符中间截断；只取预览所需行数。
        with path.open("rb") as handle:
            raw = b"".join(handle.readlines()[:12])
        text, _ = decode_text(raw)
        table, _ = read_csv_table(text, ",")
    elif suffix in {".xls", ".xlsx"}:
        if isinstance(header_row, bool) or not isinstance(header_row, Integral) or header_row < 0:
            raise ValueError("Excel 表头行必须是非负整数；0 表示第一行。")
        header_row = int(header_row)
        engine = "xlrd" if suffix == ".xls" else "openpyxl"
        with pd.ExcelFile(path, engine=engine) as workbook:
            names = workbook.sheet_names
            if isinstance(sheet, Integral) and not isinstance(sheet, bool):
                sheet_index = int(sheet)
                if not 0 <= sheet_index < len(names):
                    raise ValueError(f"工作表序号 {sheet_index} 超出范围；文件共有 {len(names)} 个工作表：{names}")
                selected_sheet = names[sheet_index]
            elif sheet in names:
                selected_sheet = sheet
            else:
                raise ValueError(f"未找到工作表 {sheet!r}；现有工作表：{names}")
            table = pd.read_excel(workbook, sheet_name=selected_sheet, header=None,
                                  skiprows=header_row, nrows=7)
        if table.empty:
            raise ValueError(f"Excel 工作表 {selected_sheet!r} 在所选表头行之后为空。")
        table.columns = table.iloc[0].tolist()
        table = table.iloc[1:]
    else:
        raise ValueError("映射预览只适用于 CSV / Excel；MEMP、SDAT 使用各自解析器。")
    if not all(isinstance(c,str) and c.strip() for c in table.columns) or len(set(table.columns))!=len(table.columns):
        raise ValueError("预览要求所选表头行包含非空、不重复的文本列名；"
                         "请检查左侧的“Excel 工作表 / 表头行”。")
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
