"""按用户指定 Python/openpyxl 技术栈导出批次快照，不在 Excel 重做复数科学计算。"""

import math
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


def write_table(workbook, name, headers, rows, widths):
    """输入表头/数据行与列宽；创建可筛选的平面数据表，数值保持数值类型。

    任意样品名等字符串强制作为文本保存，不能被 Excel 误当作公式。
    """
    sheet = workbook.create_sheet(name)
    sheet.sheet_view.showGridLines = False
    sheet.append(headers)
    for row in rows:
        sheet.append([str(value) if isinstance(value, float) and not math.isfinite(value) else value for value in row])
    for row in sheet:
        max_lines = 1
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"
            cell.font = Font(name="Arial", size=11, color="222222")
            cell.alignment = Alignment(vertical="top", wrap_text=True, horizontal="right" if isinstance(cell.value, (int, float)) else "left", indent=0 if isinstance(cell.value, (int, float)) else 1)
            if isinstance(cell.value, float):
                cell.number_format = "0.0000"
            if cell.value is not None:
                display = f"{cell.value:.4f}" if isinstance(cell.value, float) else str(cell.value)
                visual_length = sum(2 if ord(char) > 255 else 1 for char in display)
                max_lines = max(max_lines, math.ceil(visual_length/max(8, widths[cell.column-1]-2)))
        sheet.row_dimensions[row[0].row].height = min(409, max(24, max_lines*16+8))
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="34495E")
        cell.font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(right=Side(style="thin", color="FFFFFF"))
    sheet.row_dimensions[1].height = 48
    for i, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(i)].width = width
    sheet.freeze_panes = "B2"
    sheet.auto_filter.ref = sheet.dimensions
    return sheet


def export_batch_excel(path, summaries, minima, bands, provenance):
    """输入批次汇总、全部并列最优点、EAB 频段及来源；保存独立 xlsx 快照。

    Summary 的位置字段取确定性首个并列结果，所有并列值在明细表保留。
    失败样品的科学结果为空，绝不以零冒充有效计算。
    """
    workbook = Workbook()
    workbook.remove(workbook.active)
    headers = ["Sample", "Calculation status", "RLmin (dB)", "RLmin Frequency (GHz)", "Best Thickness (mm)",
               "Maximum EAB (GHz)", "Thickness at Maximum EAB (mm)", "Frequency Range of Maximum EAB (GHz)", "Validation"]
    keys = ["sample", "status", "rl_min_db", "rl_min_frequency_ghz", "best_thickness_mm", "maximum_eab_ghz",
            "thickness_at_maximum_eab_mm", "maximum_eab_frequency_ranges_ghz", "validation"]
    validation_labels = {"pending_imaginary_convention_and_commercial_reference": "Pending sign convention and reference",
                         "pending_commercial_reference": "Pending reference", "not_calculated": "Not calculated"}
    summary_rows = []
    for row in summaries:
        values = [row.get(key) for key in keys]
        values[-1] = validation_labels.get(values[-1], values[-1])
        summary_rows.append(values)
    summary_sheet = write_table(workbook, "Summary", headers, summary_rows, [28, 18, 17, 22, 22, 22, 27, 36, 32])
    for row in summary_sheet.iter_rows(min_row=2):
        row[6].border = Border(right=Side(style="thin", color="DDE2E6"))
    write_table(workbook, "RL_minima", ["Sample", "RLmin (dB)", "Frequency (GHz)", "Thickness (mm)", "At frequency boundary", "At thickness boundary"],
                [[row[k] for k in ("sample", "rl_min_db", "frequency_ghz", "thickness_mm", "at_frequency_boundary", "at_thickness_boundary")] for row in minima], [28, 20, 22, 22, 24, 24])
    write_table(workbook, "EAB_bands", ["Sample", "Thickness (mm)", "Start (GHz)", "End (GHz)", "Width (GHz)", "Touches lower boundary", "Touches upper boundary"],
                [[row[k] for k in ("sample", "thickness_mm", "start_ghz", "end_ghz", "width_ghz", "touches_lower_boundary", "touches_upper_boundary")] for row in bands], [28, 22, 20, 20, 20, 24, 24])
    write_table(workbook, "Provenance", ["Sample", "Field", "Value"], provenance, [28, 34, 90])
    workbook.save(path)
