import json
from pathlib import Path
from PySide6.QtWidgets import (QWidget, QFormLayout, QDoubleSpinBox, QLineEdit, QComboBox,
                               QCheckBox, QPushButton, QFileDialog, QLabel)
from gui.controllers.analysis_controller import AnalysisRequest, ROOT


class ParameterPanel(QWidget):
    """展示单位参数，不自动触发计算；点击分析时生成快照。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        form = QFormLayout(self)
        self.name = QLineEdit()
        form.addRow("样品名称", self.name)
        self.fields = {}
        for key, label, value, minimum, maximum, decimals in [
            ("thickness_min", "厚度下限 (mm)", 1, .0001, 1000, 4),
            ("thickness_max", "厚度上限 (mm)", 5, .0001, 1000, 4),
            ("thickness_step", "厚度步长 (mm)", .01, .0001, 1000, 4),
            ("curve_thickness", "RL 曲线厚度 (mm)", 2, .0001, 1000, 4),
            ("threshold", "RL 阈值 (dB)", -10, -1000, 0, 2),
            ("frequency_min", "频率下限 (GHz)", 2, .000001, 1000000, 6),
            ("frequency_max", "频率上限 (GHz)", 18, .000001, 1000000, 6),
        ]:
            box = QDoubleSpinBox()
            box.setDecimals(decimals)
            box.setRange(minimum, maximum)
            box.setValue(value)
            box.setSingleStep(.01 if "thickness" in key else 1)
            self.fields[key] = box
            form.addRow(label, box)
        self.crop = QCheckBox("裁选频率范围（仅保留原始点）")
        form.addRow(self.crop)
        self.unit = QComboBox()
        self.unit.addItems(["GHz", "MHz", "kHz", "Hz"])
        form.addRow("文件频率单位", self.unit)
        self.convention = QComboBox()
        self.convention.addItem("loss：损耗系数（临时假设）", "loss")
        self.convention.addItem("signed：带符号虚部", "signed")
        form.addRow("文件虚部定义", self.convention)
        self.mapping = QLineEdit()
        self.mapping.setPlaceholderText('可选：内部字段 → 源列名 JSON')
        self.mapping.setToolTip('例如 {"frequency_ghz":"频率","eps_real":"介电实部","eps_imag":"介电虚部","mu_real":"磁导实部","mu_imag":"磁导虚部"}')
        form.addRow("CSV/Excel 列映射", self.mapping)
        self.output = QLineEdit(str(ROOT / "output"))
        form.addRow("输出目录", self.output)
        choose = QPushButton("选择输出目录")
        choose.clicked.connect(self.choose_output)
        form.addRow(choose)
        hint = QLabel("缺失数据插值：OFF\n内部复数：ε′−jε″，μ′−jμ″\nEAB：−10 dB 最大连续带宽\n阈值交点：沿用核心 linear 方法\n修改参数后需点击开始分析。")
        hint.setWordWrap(True)
        form.addRow(hint)

    def choose_output(self):
        """选择输出根目录；每次运行仍创建独立子目录。"""
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output.text())
        if path:
            self.output.setText(path)

    def parser_options(self, path=None):
        """输出显式解析选项；MEMP 按原始表头 GHz，不覆盖其列映射。"""
        options = {"imaginary_convention": self.convention.currentData(), "convention_confirmed": False}
        if path is None or Path(path).suffix.lower() != ".memp":
            options["frequency_unit"] = self.unit.currentText()
            if self.mapping.text().strip():
                value = json.loads(self.mapping.text())
                if not isinstance(value, dict):
                    raise ValueError("列映射必须是 JSON 对象。")
                options["column_map"] = value
        return options

    def request(self, path):
        """输入选中文件；读取一次 UI 值，后台不会访问控件。"""
        if not self.output.text().strip():
            raise ValueError("请选择输出目录。")
        if not self.name.text().strip():
            raise ValueError("请输入样品名称。")
        values = {key: box.value() for key, box in self.fields.items()}
        if not self.crop.isChecked():
            values.update(frequency_min=None, frequency_max=None)
        return AnalysisRequest(path=Path(path), name=self.name.text().strip(),
                               output=Path(self.output.text()).expanduser().resolve(),
                               parser_options=self.parser_options(path), full_science=True, **values)
