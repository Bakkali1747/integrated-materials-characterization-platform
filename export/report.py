"""单样品中文分析报告：可编辑 DOCX 与独立 PDF，图内标签保持英文。"""

import tempfile
from datetime import datetime
from html import escape
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Table, TableStyle

from core.analysis_service import load_completed_run
from plotting.em_parameters import plot_parameters
from plotting.rl_plot import plot_rl_2d, plot_rl_curve, plot_rl_multi_thickness
from plotting.style import journal_style, plt

CHINESE_FONT = "Microsoft YaHei"
PDF_FONT = "STSong-Light"
METHODS = [
    "[COMMON] 时间因子 exp(+jωt)，εr = ε′ − jε″，μr = μ′ − jμ″；内部虚部保存损耗系数。",
    "[COMMON] 法向入射、均匀单层、理想金属背板：n = sqrt(μr εr)，z = (μr/n) tanh[j(2πfd/c)n]，"
    "RL = 20 log10 |(z−1)/(z+1)|。",
    "[COMMON] EAB 是固定厚度下 RL ≤ 阈值的最长连续频段宽度；分离频段不累加，"
    "跨厚度并集只称累计频率覆盖。",
    "[COMMON] 缺失数据不插值；负损耗、RL > 0 和负吸收不裁剪；结果最小值仅针对本次扫描网格。",
    "[COMMON] 图片数据为原计算网格，未从图像反推；图内坐标与标签使用英文，正文为中文。",
]


def _value(value, digits=6):
    if value is None:
        return "未记录"
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)


def _figure_set(run, folder, dpi):
    """生成报告用单栏图；返回 [(path, caption)]。"""
    style = journal_style("single", dpi)
    record = run.record
    items = []

    def save(fig, name, caption):
        path = folder / f"{name}.png"
        fig.savefig(path, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        items.append((path, caption))

    save(plot_parameters(run.sample, "permittivity", style), "permittivity", "图 1  ε′ / ε″ 随频率变化")
    save(plot_parameters(run.sample, "permeability", style), "permeability", "图 2  μ′ / μ″ 随频率变化")
    save(plot_rl_curve(run.curve, style=style, threshold=record["rl_threshold_db"]), "rl_curve",
         f"图 3  指定厚度 {run.curve.thickness_mm[0]:g} mm 的 RL 曲线")
    if len(run.thickness_mm) > 1:
        save(plot_rl_2d(run.result, style)[0], "rl_2d", "图 4  RL 随频率与厚度变化")
    selection = record.get("multi_thickness_rl")
    if selection:
        save(plot_rl_multi_thickness(run.result, selection["row_indices"], style,
                                     threshold=record["rl_threshold_db"]),
             "rl_multi", "图 5  代表厚度的 RL 叠加（参考线为当前阈值）")
    return items


def _report_data(run_directory):
    run = load_completed_run(run_directory)
    record, summary = run.record, run.summary
    minima = summary.get("global_minima", [])
    standard = summary.get("standard_eab", {})
    selected = summary.get("selected_threshold_bandwidth", {})
    coverage = summary.get("cumulative_frequency_coverage", {})
    configuration = record.get("configuration", {})
    source = record.get("source", {})
    best_thicknesses = standard.get("best_thicknesses", [])
    metadata = [
        ("样品", record.get("sample", "未记录")),
        ("运行状态", record.get("status", "unknown")),
        ("验证状态", record.get("validation_status", "unknown")),
        ("分析日期", record.get("analysis_date", "未记录")),
        ("软件版本", record.get("software_version", "未记录")),
        ("运行 ID", record.get("run_id", "未记录")),
        ("源文件", Path(record.get("raw_file", "")).name or "未记录"),
        ("源 SHA-256", record.get("raw_sha256", "unavailable")),
        ("频率范围 (GHz)", f"{record.get('frequency_range_ghz', ['-', '-'])[0]} – {record.get('frequency_range_ghz', ['-', '-'])[1]}"),
        ("频率点数", record.get("frequency_points", "未记录")),
        ("厚度范围 (mm)", f"{record.get('thickness_range_mm', ['-', '-'])[0]} – {record.get('thickness_range_mm', ['-', '-'])[1]}"),
        ("厚度步长 (mm)", configuration.get("thickness_step_mm", "未记录")),
        ("RL 阈值 (dB)", configuration.get("rl_threshold_db", "未记录")),
        ("EAB 交点", configuration.get("eab_threshold_crossing", "未记录")),
        ("图尺寸预设", configuration.get("figure_preset", "screen")),
        ("图 DPI", configuration.get("figure_dpi", "未记录")),
    ]
    results = []
    if minima:
        results.append(("网格 RLmin (dB)", _value(minima[0].get("rl_min_db"))))
        results.append(("RLmin 频率 (GHz)", _value(minima[0].get("frequency_ghz"))))
        results.append(("RLmin 厚度 (mm)", _value(minima[0].get("thickness_mm"))))
        results.append(("并列 RLmin 点数", len(minima)))
    results += [
        ("Maximum EAB (GHz)", _value(standard.get("maximum_bandwidth_ghz"))),
        ("最大 EAB 厚度", ", ".join(f"{item['thickness_mm']:g}" for item in best_thicknesses) or "无正宽度频段"),
        ("指定阈值最大连续带宽 (GHz)", _value(selected.get("maximum_bandwidth_ghz"))),
        ("累计频率覆盖 (GHz)", _value(coverage.get("total_coverage_ghz"))),
        ("累计覆盖范围", "; ".join(f"{a:g}–{b:g}" for a, b in coverage.get("intervals_ghz", [])) or "无"),
    ]
    warnings = list(record.get("warnings", []))
    phase2 = record.get("phase2", {})
    warnings += list(phase2.get("notes", []))
    artifacts = record.get("artifacts_sha256", {})
    provenance = [
        ("Artifacts 数量", len(artifacts)),
        ("Git commit", record.get("git", {}).get("commit", "unavailable")),
        ("构建状态", record.get("build_state", "unavailable")),
        ("解析器", record.get("parser_version", source.get("parser", "未记录"))),
        ("相位约定", record.get("complex_convention", "未记录")),
        ("缺失数据插值", record.get("missing_data_interpolation", "OFF")),
        ("原始文件绝对路径", "已省略（见原运行记录）"),
    ]
    return run, metadata, results, warnings, provenance


def _docx_table(document, rows, header=None):
    columns = len(rows[0]) if rows else 2
    table = document.add_table(rows=0, cols=columns)
    table.style = "Table Grid"
    if header:
        cells = table.add_row().cells
        for cell, text in zip(cells, header):
            cell.text = str(text)
            for paragraph in cell.paragraphs:
                for run_ in paragraph.runs:
                    run_.bold = True
                    run_.font.size = Pt(9)
    for row in rows:
        cells = table.add_row().cells
        for cell, text in zip(cells, row):
            cell.text = str(text)
            for paragraph in cell.paragraphs:
                for run_ in paragraph.runs:
                    run_.font.size = Pt(9)


def _style_docx(document):
    for name in ("Normal", "Title", "Heading 1", "Heading 2"):
        style = document.styles[name]
        style.font.name = CHINESE_FONT
        style.element.rPr.rFonts.set(qn("w:eastAsia"), CHINESE_FONT)
    document.styles["Normal"].font.size = Pt(10.5)


def build_docx(run_directory, output, figures, metadata, results, warnings, provenance):
    document = Document()
    _style_docx(document)
    document.add_heading("微波吸收分析报告", level=0)
    document.add_paragraph(f"样品：{metadata[0][1]} ｜ 生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}")
    document.add_paragraph("本报告由本地分析记录自动生成；验证状态以运行记录为准，不因导出报告而升级。")
    document.add_heading("1. 基本信息", level=1)
    _docx_table(document, metadata)
    document.add_heading("2. 结果摘要", level=1)
    _docx_table(document, results)
    document.add_heading("3. 图", level=1)
    for path, caption in figures:
        document.add_picture(str(path), width=Cm(14))
        document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph = document.add_paragraph(caption)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run_ in paragraph.runs:
            run_.font.size = Pt(9)
            run_.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    document.add_heading("4. 质量警告与边界", level=1)
    if warnings:
        for warning in warnings[:20]:
            document.add_paragraph(str(warning), style="List Bullet")
        if len(warnings) > 20:
            document.add_paragraph("仅显示前 20 条；完整记录见原运行目录 analysis_record.json。")
    else:
        document.add_paragraph("本次运行未记录额外警告。")
    document.add_heading("5. 方法与模型边界", level=1)
    for note in METHODS:
        document.add_paragraph(note)
    document.add_heading("6. 追溯", level=1)
    _docx_table(document, provenance)
    document.save(output)
    return output


def _pdf_styles():
    pdfmetrics.registerFont(UnicodeCIDFont(PDF_FONT))
    return {
        "title": ParagraphStyle("title", fontName=PDF_FONT, fontSize=17, leading=23, spaceAfter=10),
        "subtitle": ParagraphStyle("subtitle", fontName=PDF_FONT, fontSize=9, leading=13, textColor=colors.grey),
        "h1": ParagraphStyle("h1", fontName=PDF_FONT, fontSize=12, leading=18, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("body", fontName=PDF_FONT, fontSize=9.5, leading=14, spaceAfter=3),
        "caption": ParagraphStyle("caption", fontName=PDF_FONT, fontSize=8.5, leading=12,
                                  textColor=colors.grey, alignment=1, spaceAfter=8),
    }


def _pdf_table(rows, styles):
    data = [[Paragraph(escape(str(cell)), styles["body"]) for cell in row] for row in rows]
    table = Table(data, colWidths=[4.2*cm, 12.3*cm] if rows and len(rows[0]) == 2 else None)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), .4, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
    ]))
    return table


def build_pdf(output, figures, metadata, results, warnings, provenance):
    styles = _pdf_styles()
    document = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                                 topMargin=1.8*cm, bottomMargin=1.8*cm)
    story = [Paragraph("微波吸收分析报告", styles["title"]),
             Paragraph(escape(f"样品：{metadata[0][1]} ｜ 生成时间："
                              f"{datetime.now().astimezone().isoformat(timespec='seconds')}"), styles["subtitle"]),
             Paragraph("本报告由本地分析记录自动生成；验证状态以运行记录为准，不因导出报告而升级。", styles["subtitle"]),
             Paragraph("1. 基本信息", styles["h1"]), _pdf_table(metadata, styles),
             Paragraph("2. 结果摘要", styles["h1"]), _pdf_table(results, styles),
             Paragraph("3. 图", styles["h1"])]
    for path, caption in figures:
        width, height = PILImage.open(path).size
        image_width = 15*cm
        story.append(Image(str(path), width=image_width, height=image_width*height/width))
        story.append(Paragraph(escape(caption), styles["caption"]))
    story.append(Paragraph("4. 质量警告与边界", styles["h1"]))
    if warnings:
        for warning in warnings[:20]:
            story.append(Paragraph("• " + escape(str(warning)), styles["body"]))
        if len(warnings) > 20:
            story.append(Paragraph("仅显示前 20 条；完整记录见 analysis_record.json。", styles["body"]))
    else:
        story.append(Paragraph("本次运行未记录额外警告。", styles["body"]))
    story.append(Paragraph("5. 方法与模型边界", styles["h1"]))
    for note in METHODS:
        story.append(Paragraph(escape(note), styles["body"]))
    story.append(Paragraph("6. 追溯", styles["h1"]))
    story.append(_pdf_table(provenance, styles))
    document.build(story)
    return output


def export_report(run_directory, output_path, formats=("docx", "pdf"), dpi=300):
    """输入已完成运行目录与输出基名；返回实际生成的文件列表。"""
    run_directory = Path(run_directory).resolve()
    output = Path(output_path)
    base = output.with_suffix("") if output.suffix.lower() in {".docx", ".pdf"} else output
    run, metadata, results, warnings, provenance = _report_data(run_directory)
    generated = []
    with tempfile.TemporaryDirectory() as temporary:
        figures = _figure_set(run, Path(temporary), dpi)
        if "docx" in formats:
            target = base.with_suffix(".docx")
            target.parent.mkdir(parents=True, exist_ok=True)
            build_docx(run_directory, target, figures, metadata, results, warnings, provenance)
            generated.append(target)
        if "pdf" in formats:
            target = base.with_suffix(".pdf")
            target.parent.mkdir(parents=True, exist_ok=True)
            build_pdf(target, figures, metadata, results, warnings, provenance)
            generated.append(target)
    return generated
