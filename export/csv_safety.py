"""CSV 导出防护：只把“看起来像公式”的字符串转义，不改数值列。"""

import pandas as pd


def safe_cell(value):
    """输入单元格值；返回可直接写入 CSV 的值。

    以 = + - @ 或制表符/回车开头的字符串可能被 Excel 当作公式；
    纯数值（如 -1.5、+2）保持原样，避免把数字变成文本。
    """
    if not isinstance(value, str) or not value:
        return value
    if value[0] not in "=+-@\t\r":
        return value
    try:
        float(value)
    except ValueError:
        return "'" + value
    return value


def escape_formula_cells(frame):
    """输入 DataFrame；复制并转义文本列中的潜在公式单元格。"""
    output = frame.copy()
    for column in output.columns:
        series = output[column]
        if series.dtype == object or pd.api.types.is_string_dtype(series):
            output[column] = series.map(safe_cell)
    return output
