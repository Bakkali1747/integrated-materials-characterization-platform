"""XRD 分析报告：DOCX 与 PDF；不改变运行验证状态。"""

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

from core.xrd_service import load_completed_xrd_run
from export.report import _docx_table, _pdf_styles, _pdf_table, _style_docx
from plotting.style import journal_style, plt
from plotting.xrd_plot import plot_xrd_pattern, plot_xrd_phase_matches

METHODS = [
    "[COMMON] 2θ 必须严格递增；不排序、不插值、不裁剪原始强度。",
    "[COMMON] 峰位取扫描网格点；Pseudo-Voigt 拟合使用局部线性基线，R²<0.8 时保留半高插值 FWHM。",
    "[COMMON] 仪器展宽按 Gaussian 平方差校正：β_obs² = β_sample² + β_instrument²；未校正时尺寸为表观值。",
    "[COMMON] d = λ / (2 sinθ)；Scherrer D = Kλ / (β cosθ)。",
    "[COMMON] 背景扣除为可选的左右高角窗口线性拟合，默认关闭；峰检测平滑不改变原始强度。",
    "[COMMON] 参考相匹配是按容差的峰位筛查，不是物相鉴定；分数不证明样品只含该相。",
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

    save(plot_xrd_pattern(table, metrics, style), "xrd_pattern", "图 1  XRD 图谱与检测峰")
    if metrics.get("reference_matching"):
        save(plot_xrd_phase_matches(table, metrics, style), "xrd_phase_matches",
             "图 2  参考相峰位匹配（筛查）")
    return items


def _report_data(directory):
    saved = load_completed_xrd_run(directory)
    record, metrics = saved["record"], saved["metrics"]
    background = metrics.get("background") or {}
    configuration = record.get("configuration", {})
    library_info = (metrics.get("quality") or {}).get("phase_library") or {}
    metadata = [
        ("样品", record.get("sample", "未记录")),
        ("运行状态", record.get("status", "unknown")),
        ("验证状态", record.get("validation_status", "unknown")),
        ("分析日期", record.get("analysis_date", "未记录")),
        ("软件版本", record.get("software_version", "未记录")),
        ("运行 ID", record.get("run_id", "未记录")),
        ("源文件", Path(record.get("raw_file", "")).name or "未记录"),
        ("源 SHA-256", record.get("raw_sha256", "unavailable")),
        ("2θ 范围 (°)", str(record.get("two_theta_range_deg", "未记录"))),
        ("数据点数", record.get("point_count", "未记录")),
        ("波长 (Å)", _value(configuration.get("wavelength_angstrom"))),
        ("Scherrer K", _value(configuration.get("k_factor"))),
        ("峰形拟合", "Pseudo-Voigt" if configuration.get("fit_peaks") else "关闭（半高插值）"),
        ("仪器展宽", _value(configuration.get("instrument_mode"))),
        ("仪器 FWHM (°)", _value(configuration.get("instrument_fwhm_deg"))),
        ("仪器展宽文件", Path(configuration["instrument_file"]).name
         if configuration.get("instrument_file") else "未使用"),
        ("物相库", library_info.get("source", "未使用")),
        ("背景", background.get("mode", "none")),
        ("检测峰数", len(metrics.get("peaks") or [])),
        ("图 DPI", configuration.get("figure_dpi", "未记录")),
    ]
    results = []
    for index, peak in enumerate(metrics.get("peaks") or [], 1):
        if index > 15:
            break
        results.append((f"峰 {index}", f"2θ={_value(peak.get('center_deg', peak.get('two_theta_deg')))}°, "
                                      f"I={_value(peak.get('relative_intensity_pct'))}%, "
                                      f"FWHM={_value(peak.get('fwhm_deg'))}°, "
                                      f"拟合FWHM={_value(peak.get('fwhm_fit_deg'))}°, "
                                      f"η={_value(peak.get('eta'))}, R²={_value(peak.get('fit_r_squared'))}, "
                                      f"d={_value(peak.get('d_angstrom'))} Å, "
                                      f"D={_value(peak.get('crystallite_size_nm'))} nm"))
    if len(metrics.get("peaks") or []) > 15:
        results.append(("更多峰", f"仅显示前 15 个；完整 {len(metrics['peaks'])} 个见 xrd_peaks.csv。"))
    for phase in metrics.get("reference_matching") or []:
        results.append((f"参考相 {phase['phase']}", f"score={phase['score']:.3f}；"
                                                    f"{phase['matched_count']}/{phase['reference_count']} 峰匹配"))
    for combo in metrics.get("phase_combinations") or []:
        results.append((f"候选组合 {' + '.join(combo['phases'])}",
                        f"覆盖 {combo['matched_observed_count']}/{combo['observed_count']} 峰；"
                        f"权重 {combo['observed_coverage']:.1%}（仅筛查）"))
    for match in (metrics.get("library_matches") or [])[:8]:
        name = match.get("mineral") or match.get("formula") or f"COD {match['phase_id']}"
        results.append((f"COD 候选 {name}",
                        f"score={match['score']:.3f}；匹配 {match['matched_count']}/{match['reference_count']}；"
                        f"实测覆盖 {match['observed_coverage']:.1%}（仅筛查）"))
    warnings = list(record.get("warnings") or [])
    artifacts = record.get("artifacts_sha256", {})
    provenance = [
        ("Artifacts 数量", len(artifacts)),
        ("Git commit", record.get("git", {}).get("commit", "unavailable")),
        ("构建状态", record.get("build_state", "unavailable")),
        ("解析器", record.get("parser_version", "未记录")),
        ("缺失数据插值", "OFF"),
        ("平滑", "OFF"),
        ("排序", "preserved"),
        ("原始文件绝对路径", "已省略（见原运行记录）"),
    ]
    return saved, metadata, results, warnings, provenance


def build_docx(output, figures, metadata, results, warnings, provenance):
    document = Document()
    _style_docx(document)
    document.add_heading("XRD 峰分析报告", level=0)
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
    story = [Paragraph("XRD 峰分析报告", styles["title"]),
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


def export_xrd_report(run_directory, output_path, formats=("docx", "pdf"), dpi=300):
    """输入已完成 XRD 运行目录与输出基名；返回生成的文件列表。"""
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
