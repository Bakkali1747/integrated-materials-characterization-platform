"""VSM 磁滞回线页面；单位、质量与背景扣除均为显式输入。"""

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
)

from core.vsm import inspect_vsm_table, suggest_vsm_columns
from core.vsm_service import VSMConfig
from gui.controllers.analysis_controller import ROOT
from gui.controllers.vsm_controller import (
    analyze_vsm_request,
    load_vsm_request,
    vsm_figure,
    vsm_metrics_rows,
    vsm_summary_text,
)
from gui.pages.task_page import TaskPage
from gui.widgets.plot_canvas import PlotCanvas
from gui.widgets.status_badge import StatusBadge
from plotting.style import plt


class VsmPage(TaskPage):
    analysis_completed = Signal(object)

    def __init__(self):
        super().__init__("VSM 磁滞回线分析")
        self.badge = StatusBadge("PENDING", "VSM 指标待外部参考核对；Hc/Mr 为插值估计，Ms 不是真实饱和。")
        self.layout.addWidget(self.badge)

        self.file = QLineEdit()
        self.file.setPlaceholderText("选择 VSM 原始文件（.csv / .xlsx / .xls / .txt）")
        choose = QPushButton("选择…")
        choose.clicked.connect(self.choose_file)
        row = QHBoxLayout()
        row.addWidget(QLabel("VSM 文件"))
        row.addWidget(self.file)
        row.addWidget(choose)
        self.layout.addLayout(row)

        self.name = QLineEdit()
        self.name.setPlaceholderText("样品名称")
        self.output = QLineEdit(str(ROOT / "output"))
        output_button = QPushButton("输出目录")
        output_button.clicked.connect(self.choose_output)
        row = QHBoxLayout()
        row.addWidget(QLabel("样品"))
        row.addWidget(self.name)
        row.addWidget(QLabel("输出"))
        row.addWidget(self.output)
        row.addWidget(output_button)
        self.layout.addLayout(row)

        self.field_column = QComboBox()
        self.field_column.setEditable(True)
        self.moment_column = QComboBox()
        self.moment_column.setEditable(True)
        columns_button = QPushButton("读取列名")
        columns_button.clicked.connect(self.load_columns)
        row = QHBoxLayout()
        row.addWidget(QLabel("磁场列"))
        row.addWidget(self.field_column, 1)
        row.addWidget(QLabel("磁矩列"))
        row.addWidget(self.moment_column, 1)
        row.addWidget(columns_button)
        self.layout.addLayout(row)

        self.field_unit = QComboBox()
        for unit in ("Oe", "A/m", "kA/m", "T", "mT"):
            self.field_unit.addItem(unit, unit)
        self.moment_unit = QComboBox()
        for unit in ("emu", "A m^2"):
            self.moment_unit.addItem(unit, unit)
        self.mass = QLineEdit()
        self.mass.setPlaceholderText("样品质量 mg；留空则仅报告磁矩")
        self.mass_from_header = False
        self.mass.textEdited.connect(self._mass_edited)
        self.sheet = QLineEdit("0")
        self.sheet.setMaximumWidth(56)
        self.header_row = QLineEdit("0")
        self.header_row.setMaximumWidth(56)
        row = QHBoxLayout()
        row.addWidget(QLabel("磁场单位"))
        row.addWidget(self.field_unit)
        row.addWidget(QLabel("磁矩单位"))
        row.addWidget(self.moment_unit)
        row.addWidget(QLabel("质量 (mg)"))
        row.addWidget(self.mass, 1)
        row.addWidget(QLabel("工作表"))
        row.addWidget(self.sheet)
        row.addWidget(QLabel("表头行"))
        row.addWidget(self.header_row)
        self.layout.addLayout(row)

        self.background = QComboBox()
        self.background.addItem("不扣除背景", "none")
        self.background.addItem("高场线性背景", "linear_high_field")
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(1.0, 1e7)
        self.threshold.setDecimals(0)
        self.threshold.setValue(10000.0)
        self.threshold.setSuffix(" Oe")
        self.threshold.setEnabled(False)
        self.background.currentIndexChanged.connect(
            lambda _: self.threshold.setEnabled(self.background.currentData() == "linear_high_field"))
        row = QHBoxLayout()
        row.addWidget(QLabel("背景"))
        row.addWidget(self.background)
        row.addWidget(QLabel("拟合窗口 |H| ≥"))
        row.addWidget(self.threshold)
        self.start_button = QPushButton("开始 VSM 分析")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start_analysis)
        row.addWidget(self.start_button)
        self.layout.addLayout(row)

        self.plot = PlotCanvas()
        self.plot.set_placeholder("选择 VSM 文件并开始分析\n磁滞回线与背景扣除图将在此显示")
        self.plot.preview_requested.connect(self.preview_figure)
        self.summary = QTextBrowser()
        self.summary.setMinimumWidth(300)
        self.summary.setPlainText("完成 VSM 分析后，这里显示 Hc、Mr、Ms、背景扣除与警告。")
        self.metrics = QTableWidget(0, 3)
        self.metrics.setHorizontalHeaderLabels(["指标", "数值", "单位"])
        self.metrics.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.metrics.horizontalHeader().setStretchLastSection(True)
        self.metrics.setMaximumHeight(260)
        side = QSplitter()
        side.setOrientation(Qt.Orientation.Vertical)
        side.addWidget(self.summary)
        side.addWidget(self.metrics)
        split = QSplitter()
        split.addWidget(self.plot)
        split.addWidget(side)
        split.setSizes([800, 360])
        self.layout.addWidget(split, 1)

        self.points = QTableWidget()
        self.points.setMaximumHeight(150)
        self.points.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.layout.addWidget(self.points)

        row = QHBoxLayout()
        self.save_button = QPushButton("保存当前图")
        self.save_button.clicked.connect(self.save_selected)
        self.save_all_button = QPushButton("导出全部图片")
        self.save_all_button.clicked.connect(self.save_all)
        self.report_button = QPushButton("导出 VSM 报告…")
        self.report_button.clicked.connect(self.save_report)
        self.open_button = QPushButton("打开结果目录")
        self.open_button.clicked.connect(self.open_output)
        for button in (self.save_button, self.save_all_button, self.report_button, self.open_button):
            row.addWidget(button)
        row.addStretch()
        self.layout.addLayout(row)

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 VSM 原始文件", "",
            "VSM 数据 (*.csv *.xlsx *.xls *.txt *.dat);;Lake Shore DAT (*.dat);;所有文件 (*)")
        if path:
            self.file.setText(path)
            self.name.setText(Path(path).stem)
            self.load_columns()

    def _mass_edited(self, _text):
        """用户手动改质量后不再标记为 DAT 文件头来源。"""
        self.mass_from_header = False

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output.text())
        if path:
            self.output.setText(path)

    def load_columns(self):
        """读取表头并给出唯一别名建议；失败只提示，不阻止手工输入。"""
        path = self.file.text().strip()
        if not path:
            return
        try:
            preview = inspect_vsm_table(path, sheet=self._sheet(), header_row=self._header_row())
        except Exception as error:
            self.show_error(f"读取列名失败：{error}")
            return
        field, moment = suggest_vsm_columns(preview["columns"])
        metadata = preview["metadata"]
        if metadata.get("field_unit"):
            self.field_unit.setCurrentText(metadata["field_unit"])
        if metadata.get("moment_unit"):
            self.moment_unit.setCurrentText(metadata["moment_unit"])
        auto_mass = metadata.get("mass_mg")
        if auto_mass is not None and (not self.mass.text().strip() or self.mass_from_header):
            self.mass.setText(f"{float(auto_mass):.6g}")
            self.mass_from_header = True
        for combo, suggested in ((self.field_column, field), (self.moment_column, moment)):
            current = combo.currentText().strip()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(preview["columns"])
            if suggested:
                combo.setCurrentText(suggested)
            elif current in preview["columns"]:
                combo.setCurrentText(current)
            combo.blockSignals(False)
        hint = f"读取到 {len(preview['columns'])} 列、{preview['rows']} 行；请确认磁场列与磁矩列。"
        if metadata.get("dat_metadata"):
            hint = (f"Lake Shore DAT：{len(preview['columns'])} 列、{preview['rows']} 行；"
                    f"文件头 Mass(g)={metadata.get('dat_metadata', {}).get('mass_g', '未记录')}，"
                    f"单位={metadata.get('dat_metadata', {}).get('unit', 'CGS')}。请确认质量。")
        self.message.emit(hint)

    def _sheet(self):
        text = self.sheet.text().strip()
        try:
            return int(text)
        except ValueError:
            return text

    def _header_row(self):
        try:
            return int(self.header_row.text().strip() or 0)
        except ValueError:
            raise ValueError("表头行必须是非负整数。") from None

    def _mass(self):
        text = self.mass.text().strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            raise ValueError("样品质量必须是数值（mg）。") from None
        if value <= 0:
            raise ValueError("样品质量必须大于 0 mg。")
        return value

    def _config(self):
        path, name, output = self.file.text().strip(), self.name.text().strip(), self.output.text().strip()
        if not path or not name or not output:
            raise ValueError("请指定 VSM 文件、样品名称和输出目录。")
        if not Path(path).is_file():
            raise ValueError(f"原始文件不存在：{path}")
        field_column = self.field_column.currentText().strip() or None
        moment_column = self.moment_column.currentText().strip() or None
        if field_column and moment_column and field_column == moment_column:
            raise ValueError("磁场列和磁矩列不能相同。")
        return VSMConfig(path=Path(path), name=name, output=Path(output),
                         field_column=field_column, moment_column=moment_column,
                         field_unit=self.field_unit.currentData(),
                         moment_unit=self.moment_unit.currentData(),
                         mass_mg=self._mass(), sheet=self._sheet(), header_row=self._header_row(),
                         mass_from_header=self.mass_from_header,
                         background_mode=self.background.currentData(),
                         background_min_field_oe=float(self.threshold.value()),
                         dpi=self.export_dpi, entry_point="gui_vsm")

    def start_analysis(self):
        try:
            config = self._config()
        except Exception as error:
            self.show_error(str(error))
            return
        self.badge.set_status("PENDING", "VSM 指标待外部参考核对；Hc/Mr 为插值估计，Ms 不是真实饱和。")
        self.launch(lambda progress, cancelled: analyze_vsm_request(config, progress, cancelled),
                    self.analyzed)

    def analyzed(self, result):
        self.completed = result
        self._display(result)
        self.analysis_completed.emit(result)

    def _display(self, result):
        record, metrics = result["record"], result["metrics"]
        self.summary.setPlainText(vsm_summary_text(record, metrics))
        rows = vsm_metrics_rows(metrics)
        self.metrics.setRowCount(len(rows))
        for index, (label, value, unit) in enumerate(rows):
            self.metrics.setItem(index, 0, QTableWidgetItem(label))
            self.metrics.setItem(index, 1, QTableWidgetItem("不可计算" if value is None else f"{float(value):.6g}"))
            self.metrics.setItem(index, 2, QTableWidgetItem(unit))
        table = result["table"]
        columns = [column for column in ("source_row", "field_oe", "field_am", "moment_emu",
                                         "corrected_moment_emu", "analysis_value")
                   if column in table.columns]
        shown = table[columns].head(500)
        self.points.setRowCount(len(shown))
        self.points.setColumnCount(len(columns))
        self.points.setHorizontalHeaderLabels(columns)
        for row_index, values in enumerate(shown.itertuples(index=False, name=None)):
            for column_index, value in enumerate(values):
                text = f"{value:.8g}" if isinstance(value, float) else str(value)
                self.points.setItem(row_index, column_index, QTableWidgetItem(text))
        if len(table) > 500:
            self.summary.append(f"\n仅预览前 500 行；完整 {len(table)} 行见 parsed_data.csv。")
        self.plot.set_figures(result["figures"])
        if record.get("status") == "not_computable":
            self.badge.set_status("NOT_COMPUTABLE", "当前数据未能计算全部磁滞指标；详见警告。")
        else:
            self.badge.set_status("PENDING", "VSM 指标已完成；外部参考核对仍待进行。")
        self.message.emit(f"VSM 分析完成：{result['directory']}")

    def preview_figure(self, key):
        if not self.completed or self.busy:
            return
        result, dpi = self.completed, 100
        def operation(progress, cancelled):
            figure = vsm_figure(result, key, dpi)
            plt.close(figure)
            return figure
        def ready(figure):
            self.plot.install_preview(key, figure)
        self.launch(operation, ready)

    def save_selected(self):
        if not self.completed:
            return
        key = self.plot.selector.currentData() or "hysteresis"
        result, dpi = self.completed, self.export_dpi
        self.save_plot(lambda: vsm_figure(result, key, dpi))

    def save_all(self):
        if not self.completed:
            return
        result, dpi = self.completed, self.export_dpi
        self.save_all_plots({key: (lambda k=key: vsm_figure(result, k, dpi)) for key in result["figures"]})

    def save_report(self):
        if not self.completed:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 VSM 报告", "vsm_report.docx",
                                              "Word (*.docx);;PDF (*.pdf)")
        if not path:
            return
        directory, dpi = self.completed["directory"], self.export_dpi
        from export.vsm_report import export_vsm_report

        def operation(progress, cancelled):
            progress(10, "生成 VSM 报告")
            return export_vsm_report(directory, path, formats=("docx", "pdf"), dpi=dpi)
        self.launch(operation, lambda files: self.message.emit(
            "VSM 报告已保存：" + "；".join(str(item) for item in files)))

    def open_completed_run(self, directory):
        """载入工作区已登记的 VSM 运行；只读取保存产物，不重新计算。"""
        if self.busy:
            self.message.emit("当前任务运行中，请稍后再载入 VSM 运行。")
            return False
        try:
            result = load_vsm_request(directory)
        except Exception as error:
            logging.getLogger("microwave.gui").exception("载入 VSM 运行失败")
            self.show_error(f"无法载入 VSM 运行：{error}")
            return False
        self.completed = result
        self.file.setText(result["record"].get("raw_file", ""))
        self.name.setText(result["record"].get("sample", ""))
        self._display(result)
        self.message.emit("已载入工作区登记的 VSM 运行；未重新计算。")
        return True
