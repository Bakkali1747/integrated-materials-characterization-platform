"""VSM 分析报告：可编辑 DOCX 与独立 PDF；不改变运行验证状态。"""

import tempfile
from datetime import datetime
from html import escape
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate

from core.vsm_service import load_completed_vsm_run
from export.report import _docx_table, _pdf_styles, _pdf_table, _style_docx
from plotting.style import journal_style, plt
from plotting.vsm_plot import plot_background, plot_hysteresis

METHODS = [
    "[COMMON] 磁场单位在解析时显式换算为 Oe 与 A/m；1 Oe = 1000/(4π) A/m。",
    "[COMMON] 磁矩原始单位 emu 或 A·m²；质量归一化仅在提供样品质量时执行，"
    "1 emu/g = 1 A·m²/kg。",
    "[COMMON] Hc、Mr 由相邻离散点线性插值；Ms 取最大场处端值，不代表真实饱和。",
    "[COMMON] 背景扣除为可选的高场线性拟合，默认关闭；拟合窗口、系数和 R² 写入运行记录。",
    "[COMMON] 磁场扫描顺序原样保留；不排序、不去重、不插值、不裁剪，缺失值直接报错。",
    "[COMMON] 图片数据来自同一分析表，未从图像反推；图内标签使用英文，正文为中文。",
]


def _value(value, digits=6):
    if value is None:
        return "不可计算"
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)


def _figure_set(table, metrics, folder, dpi):
    style = journal_style("single", dpi)
    items = []

    def save(fig, name, caption):
        path = folder / f"{name}.png"
        fig.savefig(path, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        items.append((path, caption))

    save(plot_hysteresis(table, metrics, style), "vsm_loop", "图 1  VSM 磁滞回线")
    save(plot_hysteresis(table, metrics, style, zoom=True), "vsm_zoom", "图 2  原点附近的磁滞回线")
    if (metrics.get("background") or {}).get("mode") == "linear_high_field":
        save(plot_background(table, metrics, style), "vsm_background", "图 3  高场线性背景扣除")
    return items


def _report_data(directory):
    saved = load_completed_vsm_run(directory)
    record, metrics = saved["record"], saved["metrics"]
    background = metrics.get("background") or {}
    unit = metrics.get("metrics_unit") or "emu"
    metadata = [
        ("样品", record.get("sample", "未记录")),
        ("运行状态", record.get("status", "unknown")),
        ("验证状态", record.get("validation_status", "unknown")),
        ("分析日期", record.get("analysis_date", "未记录")),
        ("软件版本", record.get("software_version", "未记录")),
        ("运行 ID", record.get("run_id", "未记录")),
        ("源文件", Path(record.get("raw_file", "")).name or "未记录"),
        ("源 SHA-256", record.get("raw_sha256", "unavailable")),
        ("磁场范围 (Oe)", str(record.get("field_range_oe", "未记录"))),
        ("数据点数", record.get("field_points", "未记录")),
        ("样品质量 (mg)", _value(record.get("mass_mg"))),
        ("质量归一化", "是" if record.get("mass_normalization") else "否（仅磁矩）"),
        ("背景扣除", background.get("mode", "none")),
        ("背景拟合窗口 (Oe)", _value(background.get("minimum_abs_field_oe"))),
        ("图 DPI", record.get("configuration", {}).get("figure_dpi", "未记录")),
    ]
    results = [
        ("Hc (Oe)", _value(metrics.get("Hc_oe"))),
        ("Hc (A/m)", _value(metrics.get("Hc_am"))),
        ("Hc+ (Oe)", _value(metrics.get("Hc_positive_oe"))),
        ("Hc- (Oe)", _value(metrics.get("Hc_negative_oe"))),
        (f"Mr ({unit})", _value(metrics.get("Mr"))),
        (f"Mr+ ({unit})", _value(metrics.get("Mr_positive"))),
        (f"Mr- ({unit})", _value(metrics.get("Mr_negative"))),
        (f"Ms ({unit})", _value(metrics.get("Ms"))),
        (f"Ms+ ({unit})", _value(metrics.get("Ms_positive"))),
        (f"Ms- ({unit})", _value(metrics.get("Ms_negative"))),
        ("Mr/Ms", _value(metrics.get("squareness"))),
        (f"回线闭合差 ({unit})", _value(metrics.get("loop_closure"))),
        ("最大场 (Oe)", _value(metrics.get("saturation_field_oe"))),
    ]
    warnings = list(record.get("warnings") or [])
    artifacts = record.get("artifacts_sha256", {})
    provenance = [
        ("Artifacts 数量", len(artifacts)),
        ("Git commit", record.get("git", {}).get("commit", "unavailable")),
        ("构建状态", record.get("build_state", "unavailable")),
        ("解析器", record.get("parser_version", "未记录")),
        ("缺失数据插值", "OFF"),
        ("排序", "preserved"),
        ("原始文件绝对路径", "已省略（见原运行记录）"),
    ]
    return saved, metadata, results, warnings, provenance


def build_docx(output, figures, metadata, results, warnings, provenance):
    document = Document()
    _style_docx(document)
    document.add_heading("VSM 磁滞回线分析报告", level=0)
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


def build_pdf(output, figures, metadata, results, warnings, provenance):
    styles = _pdf_styles()
    document = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                                 topMargin=1.8*cm, bottomMargin=1.8*cm)
    story = [Paragraph("VSM 磁滞回线分析报告", styles["title"]),
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


def export_vsm_report(run_directory, output_path, formats=("docx", "pdf"), dpi=300):
    """输入已完成 VSM 运行目录与输出基名；返回生成的文件列表。"""
    run_directory = Path(run_directory).resolve()
    output = Path(output_path)
    base = output.with_suffix("") if output.suffix.lower() in {".docx", ".pdf"} else output
    saved, metadata, results, warnings, provenance = _report_data(run_directory)
    generated = []
    with tempfile.TemporaryDirectory() as temporary:
        figures = _figure_set(saved["table"], saved["metrics"], Path(temporary), dpi)
        if "docx" in formats:
            target = base.with_suffix(".docx")
            target.parent.mkdir(parents=True, exist_ok=True)
            build_docx(target, figures, metadata, results, warnings, provenance)
            generated.append(target)
        if "pdf" in formats:
            target = base.with_suffix(".pdf")
            target.parent.mkdir(parents=True, exist_ok=True)
            build_pdf(target, figures, metadata, results, warnings, provenance)
            generated.append(target)
    return generated
