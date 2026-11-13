from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.status_badge import StatusBadge


class HomePage(QWidget):
    navigate = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 14, 8, 8)
        layout.setSpacing(10)
        title = QLabel("综合材料表征分析平台")
        title.setObjectName("heroTitle")
        layout.addWidget(title)
        self.subtitle = QLabel("本地科研工作区 · 项目 / 样品 / 测试 / 分析运行 / 电磁 / VSM / XRD / 历史\n"
                               "Phase D 已接入 XRD 峰分析；所有结果保持待验证状态")
        self.subtitle.setObjectName("heroSubtitle")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)
        section = QLabel("快速开始")
        section.setObjectName("sectionTitle")
        layout.addWidget(section)
        self.actions = []
        self.actions_grid = QGridLayout()
        self.actions_grid.setSpacing(10)
        layout.addLayout(self.actions_grid)
        for number, (text, detail, index) in enumerate([
            ("项目与样品", "创建项目、样品并关联不同类型的测试", 1),
            ("电磁性能", "ε/μ → RL 曲线、二维图、EAB 与科研图", 2),
            ("VSM 分析", "磁滞回线、Hc / Mr / Ms 与背景扣除", 3),
            ("XRD 分析", "峰检测、FWHM、Scherrer 尺寸与参考峰匹配", 4),
            ("S 参数分析", "幅度 / dB / 相位 / RTA / SE / Smith", 5),
            ("多样品比较", "十项指标与原始网格比较", 6),
            ("批量分析", "同目录来源分组与失败隔离", 7),
            ("打开历史结果", "只读摘要、QC、产物核验与报告", 8),
            ("设置", "界面模式、默认厚度、DPI 与输出目录", 9),
        ], 1):
            button = QPushButton(f"{number:02d}  {text}\n{detail}")
            button.setObjectName("quickAction")
            button.setMinimumHeight(62)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda checked=False, i=index: self.navigate.emit(i))
            self.actions.append((button, index, text, detail))
        self._relayout(False)
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
        assumptions = QFrame()
        assumptions.setObjectName("infoCard")
        assumption_layout = QVBoxLayout(assumptions)
        assumption_layout.setContentsMargins(14, 12, 14, 12)
        assumption_layout.setSpacing(8)
        assumption_title = QLabel("计算约定")
        assumption_title.setObjectName("infoTitle")
        assumption_layout.addWidget(assumption_title)
        chips = QHBoxLayout()
        chips.setSpacing(8)
        for text in ("法向入射", "均匀单层", "理想金属背板", "EAB 连续带宽", "缺失数据不插值"):
            chip = QLabel(text)
            chip.setObjectName("assumptionChip")
            chips.addWidget(chip)
        chips.addStretch()
        assumption_layout.addLayout(chips)
        layout.addWidget(assumptions)
        layout.addStretch()

    def set_simple(self, simple):
        """日常模式隐藏 S 参数 / 比较 / 批量入口。"""
        for button, index, _, _ in self.actions:
            button.setVisible(not simple or index not in {5, 6, 7})
        self._relayout(simple)
        self.subtitle.setText(
            "本地科研工作区 · 项目 / 样品 / 电磁 / VSM / XRD / 历史\nPhase D 已接入 XRD 峰分析；缺失数据插值固定 OFF"
            if simple else
            "本地科研工作区 · 项目 / 样品 / 测试 / 分析运行 / 电磁 / VSM / XRD / 历史\n"
            "Phase D 已接入 XRD 峰分析；所有结果保持待验证状态")

    def _relayout(self, simple):
        """只把当前可见入口排成两列；奇数个时最后一张横跨两列。"""
        for button, _, _, _ in self.actions:
            self.actions_grid.removeWidget(button)
        visible = [(button, index, text, detail) for button, index, text, detail in self.actions
                   if not simple or index not in {5, 6, 7}]
        for position, (button, _, text, detail) in enumerate(visible):
            button.setText(f"{position + 1:02d}  {text}\n{detail}")
            if position == len(visible) - 1 and len(visible) % 2:
                self.actions_grid.addWidget(button, position // 2, 0, 1, 2)
            else:
                self.actions_grid.addWidget(button, position // 2, position % 2)
