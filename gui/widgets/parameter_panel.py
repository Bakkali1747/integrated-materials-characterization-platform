import json
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from gui.controllers.analysis_controller import ROOT, AnalysisRequest


class ParameterPanel(QWidget):
    """展示单位参数，不自动触发计算；点击分析时生成快照。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure_dpi = 300
        form = QFormLayout(self)
        self.form = form
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
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
        self.eab_crossing = QComboBox()
        self.eab_crossing.addItem("linear：相邻点线性交点（默认）", "linear")
        self.eab_crossing.addItem("sample：只用达标采样点首尾", "sample")
        form.addRow("EAB 阈值交点", self.eab_crossing)
        self.quarter_orders = QLineEdit("1")
        self.quarter_orders.setPlaceholderText("正奇数，逗号分隔，例如 1,3,5")
        form.addRow("四分之一波长阶数", self.quarter_orders)
        self.impedance_tolerance = QDoubleSpinBox()
        self.impedance_tolerance.setRange(.01, .99)
        self.impedance_tolerance.setDecimals(2)
        self.impedance_tolerance.setSingleStep(.05)
        self.impedance_tolerance.setValue(.1)
        form.addRow("阻抗模长显示容差 ±", self.impedance_tolerance)
        self.figure_preset = QComboBox()
        self.figure_preset.addItem("屏幕 / 默认", "screen")
        self.figure_preset.addItem("期刊单栏（3.5 in）", "single")
        self.figure_preset.addItem("期刊双栏（7.0 in）", "double")
        form.addRow("论文图尺寸", self.figure_preset)
        self.unit = QComboBox()
        self.unit.addItems(["GHz", "MHz", "kHz", "Hz"])
        form.addRow("文件频率单位", self.unit)
        self.sheet = QLineEdit()
        self.sheet.setPlaceholderText("Excel 工作表名称或序号；留空=第一个")
        self.sheet.setToolTip("工作表名称区分大小写；填写 0、1… 表示第几个工作表。CSV/MEMP 忽略此项。")
        form.addRow("Excel 工作表", self.sheet)
        self.header_row = QSpinBox()
        self.header_row.setRange(1, 10000)
        self.header_row.setValue(1)
        self.header_row.setSuffix(" 行")
        self.header_row.setToolTip("表头所在行（从 1 开始）；标题/说明行在表头之前。CSV/MEMP 忽略此项。")
        form.addRow("Excel 表头行", self.header_row)
        self.convention = QComboBox()
        self.convention.setMinimumContentsLength(10)
        self.convention.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.convention.addItem("loss：损耗系数（临时假设）", "loss")
        self.convention.addItem("signed：带符号虚部", "signed")
        form.addRow("文件虚部定义", self.convention)
        self.mapping = QLineEdit()
        self.mapping.setPlaceholderText('可选：内部字段 → 源列名 JSON')
        self.mapping.setToolTip('例如 {"frequency_ghz":"频率","eps_real":"介电实部","eps_imag":"介电虚部","mu_real":"磁导实部","mu_imag":"磁导虚部"}')
        form.addRow("CSV/Excel 列映射", self.mapping)
        self.mapping_button = QPushButton("可视化列映射 / 导入模板…")
        form.addRow(self.mapping_button)
        self.quick_preview = QCheckBox("快速预览（高清图片稍后手动导出）")
        self.quick_preview.setToolTip("数值表照常保存；只预览基础图，其余图按需生成。保持默认完整自动导出行为。")
        form.addRow(self.quick_preview)
        self.reuse = QCheckBox("批量复用相同源 + 配置的已完成运行")
        self.reuse.setToolTip("仅在批量页生效；匹配源 SHA-256 与数值配置，复用目录记录在 reused_from。")
        form.addRow(self.reuse)
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

    def apply_defaults(self, values):
        for key in ("thickness_min", "thickness_max", "thickness_step", "curve_thickness", "threshold"):
            self.fields[key].setValue(values[key])
        self.unit.setCurrentText(values["frequency_unit"])
        self.output.setText(values["output"])
        self.figure_dpi = values["dpi"]

    def parser_options(self, path=None):
        """输出显式解析选项；MEMP 按原始表头 GHz，不覆盖其列映射。"""
        options = {"imaginary_convention": self.convention.currentData(), "convention_confirmed": False}
        if path is None or Path(path).suffix.lower() != ".memp":
            options["frequency_unit"] = self.unit.currentText()
            options["header_row"] = self.header_row.value() - 1
            sheet = self.sheet.text().strip()
            if sheet:
                options["sheet"] = int(sheet) if sheet.isdigit() else sheet
            if self.mapping.text().strip():
                value = json.loads(self.mapping.text())
                if not isinstance(value, dict):
                    raise ValueError("列映射必须是 JSON 对象。")
                options["column_map"] = value
        return options

    def set_simple(self, simple):
        """日常模式隐藏高级参数行；完整模式恢复。"""
        advanced = (self.eab_crossing, self.quarter_orders, self.impedance_tolerance,
                    self.sheet, self.header_row, self.mapping, self.mapping_button,
                    self.quick_preview, self.reuse, self.figure_preset)
        for widget in advanced:
            widget.setVisible(not simple)
            label = self.form.labelForField(widget)
            if label is not None:
                label.setVisible(not simple)

    def request(self, path):
        """输入选中文件；读取一次 UI 值，后台不会访问控件。"""
        if not self.output.text().strip():
            raise ValueError("请选择输出目录。")
        if not self.name.text().strip():
            raise ValueError("请输入样品名称。")
        values = {key: box.value() for key, box in self.fields.items()}
        if values["thickness_min"] > values["thickness_max"]:
            raise ValueError("厚度下限不能大于上限。")
        if values["thickness_step"] <= 0:
            raise ValueError("厚度步长必须大于 0。")
        if values["curve_thickness"] <= 0:
            raise ValueError("RL 曲线厚度必须大于 0。")
        if self.crop.isChecked() and values["frequency_min"] > values["frequency_max"]:
            raise ValueError("频率下限不能大于上限。")
        raw_orders = self.quarter_orders.text().replace("，", ",").replace(" ", ",").split(",")
        try:
            orders = tuple(int(item) for item in raw_orders if item.strip())
        except ValueError:
            raise ValueError("四分之一波长阶数必须是逗号分隔的整数。") from None
        if not orders or any(order < 1 or order % 2 == 0 for order in orders) or len(set(orders)) != len(orders):
            raise ValueError("四分之一波长阶数必须是非空、不重复的正奇数。")
        if not self.crop.isChecked():
            values.update(frequency_min=None, frequency_max=None)
        return AnalysisRequest(path=Path(path), name=self.name.text().strip(),
                               output=Path(self.output.text()).expanduser().resolve(),
                               parser_options=self.parser_options(path), full_science=True,
                               quick_preview=self.quick_preview.isChecked(), dpi=self.figure_dpi,
                               eab_crossing=self.eab_crossing.currentData(),
                               quarter_wave_orders=orders,
                               impedance_tolerance=self.impedance_tolerance.value(),
                               figure_preset=self.figure_preset.currentData(),
                               reuse=self.reuse.isChecked(), **values)
