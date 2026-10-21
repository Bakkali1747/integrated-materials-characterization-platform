"""CSV 单元格不能把用户文本变成 Excel 公式。"""
import pandas as pd

from export.csv_safety import escape_formula_cells, safe_cell


def test_formula_like_text_is_prefixed():
    assert safe_cell("=1+1") == "'=1+1"
    assert safe_cell("+CMD") == "'+CMD"
    assert safe_cell("-2+3") == "'-2+3"
    assert safe_cell("@SUM(A1)") == "'@SUM(A1)"


def test_plain_text_and_numbers_unchanged():
    assert safe_cell("CIP_SiO2") == "CIP_SiO2"
    assert safe_cell("-1.5") == "-1.5"
    assert safe_cell("+2") == "+2"
    assert safe_cell(3.14) == 3.14
    assert safe_cell(None) is None


def test_escape_only_touches_text_columns():
    frame = pd.DataFrame({"sample": ["=cmd", "ok"], "value": [-1.5, 2.]})
    escaped = escape_formula_cells(frame)
    assert escaped["sample"].tolist() == ["'=cmd", "ok"]
    assert escaped["value"].tolist() == [-1.5, 2.]
    assert frame["sample"].tolist() == ["=cmd", "ok"]  # 不修改调用方对象
