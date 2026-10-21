"""单样品报告与期刊图尺寸的回归。"""

import pytest
from docx import Document

from export.report import export_report
from gui.controllers.analysis_controller import AnalysisRequest, analyze_request
from plotting.style import style_for


def test_journal_style_presets():
    assert style_for("single").width == 3.5 and style_for("single").font_size == 8
    assert style_for("double").width == 7.0
    assert style_for("screen").width == 7.0
    with pytest.raises(ValueError):
        style_for("unknown")


def test_report_docx_and_pdf(tmp_path, frame):
    source = tmp_path / "report_sample.csv"
    frame.to_csv(source, index=False)
    result = analyze_request(AnalysisRequest(source, "report_sample", output=tmp_path / "runs",
                                             thickness_max=1.1, thickness_step=.1, dpi=30,
                                             full_science=False, quick_preview=True))
    files = export_report(result["directory"], tmp_path / "analysis_report.docx")
    assert {path.suffix for path in files} == {".docx", ".pdf"}
    document = Document(str(tmp_path / "analysis_report.docx"))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "微波吸收分析报告" in text and "验证状态" in text and "方法与模型边界" in text
    assert len(document.inline_shapes) >= 4
    assert len(document.tables) >= 3
    pdf = (tmp_path / "analysis_report.pdf").read_bytes()
    assert pdf.startswith(b"%PDF") and len(pdf) > 20_000
    assert str(source) not in text  # 报告只保留源文件名，不泄露绝对路径
