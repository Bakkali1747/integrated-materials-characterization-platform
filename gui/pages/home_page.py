from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from gui.widgets.status_badge import StatusBadge


class HomePage(QWidget):
    navigate = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 14, 8, 8)
        layout.setSpacing(10)
        title = QLabel("微波吸收材料分析软件")
        title.setObjectName("heroTitle")
        layout.addWidget(title)
        subtitle = QLabel("本地科研分析 · 单样品 / S 参数 / 多样品比较 / 批量 / 历史 / 持久化设置\n"
                         "支持导入 .memp / .sdat / .xlsx / .xls / .csv；缺失数据插值固定 OFF")
        subtitle.setObjectName("heroSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        section = QLabel("快速开始")
        section.setObjectName("sectionTitle")
        layout.addWidget(section)
        for text, detail, index in [
            ("单样品分析", "ε/μ → RL 曲线、二维图、EAB 与科研图", 1),
            ("S 参数分析", "幅度 / dB / 相位 / RTA / SE / Smith", 2),
            ("多样品比较", "十项指标与原始网格比较", 3),
            ("批量分析", "同目录来源分组与失败隔离", 4),
            ("打开历史结果", "只读摘要、QC、产物核验与报告", 5),
        ]:
            button = QPushButton(f"{text}\n{detail}")
            button.setObjectName("quickAction")
            button.setMinimumHeight(64)
            button.clicked.connect(lambda checked=False, i=index: self.navigate.emit(i))
            layout.addWidget(button)
        section = QLabel("验证状态")
        section.setObjectName("sectionTitle")
        layout.addWidget(section)
        layout.addWidget(StatusBadge("PENDING", ".memp：可计算 / 待商业软件验证；虚部定义尚未确认。"))
        layout.addWidget(StatusBadge("candidate_high_confidence", ".sdat：待厂商字段顺序确认；S21/S12 顺序尚未正式验证。"))
        note = QLabel("[COMMON] Calculated RL from ε/μ 与 Measured S Parameters 是独立数据来源。\n"
                      "候选解析成功不等于厂商验证完成；报告与图片不会改变验证状态。")
        note.setObjectName("pageSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
