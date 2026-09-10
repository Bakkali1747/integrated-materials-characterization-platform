from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from gui.widgets.status_badge import StatusBadge


class HomePage(QWidget):
    navigate = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        title = QLabel("微波吸收材料分析软件")
        title.setStyleSheet("font-size: 28px; font-weight: 600;")
        layout.addWidget(title)
        layout.addWidget(QLabel("GUI Phase 1 · 本地科研分析\n支持导入 .memp / .sdat / .xlsx / .xls / .csv\n可直接拖入文件或文件夹。"))
        for text, index in [("单样品分析", 1), ("多样品比较（Phase 2）", 3), ("批量分析（Phase 3）", 4), ("打开历史结果（Phase 3）", 5)]:
            button = QPushButton(text)
            button.setMinimumHeight(58)
            button.clicked.connect(lambda checked=False, i=index: self.navigate.emit(i))
            layout.addWidget(button)
        layout.addWidget(StatusBadge("PENDING", ".memp：可计算 / 待商业软件验证；虚部定义尚未确认。"))
        layout.addWidget(StatusBadge("candidate_high_confidence", ".sdat：待厂商字段顺序确认；S21/S12 顺序尚未正式验证。"))
        layout.addWidget(QLabel("[COMMON] Calculated RL from ε/μ 与 Measured S Parameters 是独立数据来源。\n候选解析成功不等于厂商验证完成。"))
        layout.addStretch()
