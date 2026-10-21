"""显式保存和应用默认参数，不触发科学计算。"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui.controllers.settings_controller import defaults, validate_settings


class SettingsPage(QWidget):
    apply_requested = Signal(object)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("设置")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("默认设置 · 保存后应用到参数面板，重新启动仍保留")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(subtitle)
        scroll = QScrollArea(); scroll.setObjectName("panelCard"); scroll.setWidgetResizable(True)
        body = QWidget(); body.setMaximumWidth(900); form = QFormLayout(body); form.setSpacing(16)
        self.unit = QComboBox(); self.unit.addItems(["GHz", "MHz", "kHz", "Hz"])
        form.addRow("CSV / Excel 默认频率单位", self.unit)
        self.ui_mode = QComboBox()
        self.ui_mode.addItem("日常模式：只显示分析 / 历史 / 设置", "simple")
        self.ui_mode.addItem("完整功能：S 参数 / 比较 / 批量", "full")
        form.addRow("界面模式", self.ui_mode)
        self.fields = {}
        for key, label in [("thickness_min", "厚度下限 (mm)"), ("thickness_max", "厚度上限 (mm)"), ("thickness_step", "厚度步长 (mm)"), ("curve_thickness", "指定曲线厚度 (mm)"), ("threshold", "RL 阈值 (dB)")]:
            box = QDoubleSpinBox(); box.setDecimals(2 if key == "threshold" else 4); box.setRange(-1000 if key == "threshold" else .0001, 0 if key == "threshold" else 1000)
            self.fields[key] = box; form.addRow(label, box)
        self.output = QLineEdit(); form.addRow("输出目录", self.output)
        choose = QPushButton("选择输出目录"); choose.clicked.connect(self.choose_output); form.addRow(choose)
        self.dpi = QSpinBox(); self.dpi.setRange(72,1200); form.addRow("分析图片 DPI（导出至少 600）", self.dpi)
        self.format = QComboBox(); self.format.addItems(["png", "tiff", "pdf", "svg"]); form.addRow("手动导出默认图片格式", self.format)
        form.addRow("缺失数据插值", QLabel("OFF（固定，不补点、不自动修正数据）"))
        note = QLabel("分析运行按“分析图片 DPI”保存预览；手动导出图片至少 600 dpi。\n修改单位后需重新导入文件检查；MEMP 和 SDAT 仍按各自 parser/schema 解释。\n虚部约定与厂商验证状态不会通过设置自动确认。保存设置不会重新计算已有结果。")
        note.setWordWrap(True); form.addRow(note)
        scroll.setWidget(body); layout.addWidget(scroll,1)
        self.message = QLabel(); self.message.setWordWrap(True); layout.addWidget(self.message)
        self.save_button = QPushButton("保存并应用到参数面板"); self.save_button.setObjectName("primaryButton"); self.save_button.clicked.connect(self.request_apply); layout.addWidget(self.save_button)
        reset = QPushButton("恢复默认值（保存后生效）"); reset.clicked.connect(lambda: self.populate(defaults())); layout.addWidget(reset)
        self.populate(defaults())

    def populate(self, values):
        self.unit.setCurrentText(values["frequency_unit"])
        for key, field in self.fields.items():
            field.setValue(values[key])
        self.output.setText(values["output"]); self.dpi.setValue(values["dpi"]); self.format.setCurrentText(values["figure_format"])
        self.ui_mode.setCurrentIndex(max(0, self.ui_mode.findData(values.get("ui_mode", "simple"))))

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self,"选择默认输出目录",self.output.text())
        if path:
            self.output.setText(path)

    def request_apply(self):
        try:
            values = defaults()
            values.update({key:field.value() for key,field in self.fields.items()})
            values.update(frequency_unit=self.unit.currentText(), output=self.output.text(), dpi=self.dpi.value(),
                          figure_format=self.format.currentText(), ui_mode=self.ui_mode.currentData())
            self.apply_requested.emit(validate_settings(values))
        except Exception as error:
            self.message.setText(str(error))
