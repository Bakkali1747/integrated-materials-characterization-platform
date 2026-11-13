"""XRD 峰分析页面；波长、背景窗口与参考相匹配均为显式输入。"""

import logging
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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

from core.xrd import inspect_xrd_table, read_xrd, suggest_xrd_columns
from core.xrd_service import XRDConfig
from gui.controllers.analysis_controller import ROOT
from gui.controllers.xrd_controller import (
    analyze_xrd_request,
    load_xrd_request,
    xrd_figure,
    xrd_summary_text,
)
from gui.pages.task_page import TaskPage
from gui.widgets.plot_canvas import PlotCanvas
from gui.widgets.status_badge import StatusBadge
from plotting.style import plt


class XrdPage(TaskPage):
    analysis_completed = Signal(object)

    def __init__(self):
        super().__init__("XRD 峰分析")
        self.badge = StatusBadge("PENDING", "XRD 峰位与 Scherrer 尺寸待外部参考核对；未做仪器展宽校正。")
        self.layout.addWidget(self.badge)

        self.file = QLineEdit()
        self.file.setPlaceholderText("选择 XRD 原始文件（.csv / .txt / .xy / .dat）")
        choose = QPushButton("选择…")
        choose.clicked.connect(self.choose_file)
        row = QHBoxLayout()
        row.addWidget(QLabel("XRD 文件"))
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

        self.two_theta_column = QComboBox()
        self.two_theta_column.setEditable(True)
        self.intensity_column = QComboBox()
        self.intensity_column.setEditable(True)
        columns_button = QPushButton("读取列名")
        columns_button.clicked.connect(self.load_columns)
        row = QHBoxLayout()
        row.addWidget(QLabel("2θ 列"))
        row.addWidget(self.two_theta_column, 1)
        row.addWidget(QLabel("强度列"))
        row.addWidget(self.intensity_column, 1)
        row.addWidget(columns_button)
        self.layout.addLayout(row)

        self.wavelength = QDoubleSpinBox()
        self.wavelength.setRange(0.1, 5.0)
        self.wavelength.setDecimals(4)
        self.wavelength.setValue(1.5406)
        self.wavelength.setSingleStep(0.0001)
        self.wavelength.setSuffix(" Å")
        self.k_factor = QDoubleSpinBox()
        self.k_factor.setRange(0.1, 2.0)
        self.k_factor.setDecimals(3)
        self.k_factor.setValue(0.9)
        self.min_prominence = QDoubleSpinBox()
        self.min_prominence.setRange(0.0, 100.0)
        self.min_prominence.setDecimals(2)
        self.min_prominence.setValue(5.0)
        self.min_prominence.setSuffix(" %")
        self.min_distance = QDoubleSpinBox()
        self.min_distance.setRange(0.0, 10.0)
        self.min_distance.setDecimals(3)
        self.min_distance.setValue(0.1)
        self.min_distance.setSuffix(" °")
        self.smoothing = QComboBox()
        for points in (1, 3, 5, 7, 9, 15, 25):
            self.smoothing.addItem("不平滑" if points == 1 else f"{points} 点", points)
        self.smoothing.setCurrentIndex(2)
        row = QHBoxLayout()
        row.addWidget(QLabel("波长"))
        row.addWidget(self.wavelength)
        row.addWidget(QLabel("Scherrer K"))
        row.addWidget(self.k_factor)
        row.addWidget(QLabel("最小突出度"))
        row.addWidget(self.min_prominence)
        row.addWidget(QLabel("最小峰间距"))
        row.addWidget(self.min_distance)
        row.addWidget(QLabel("检测平滑"))
        row.addWidget(self.smoothing)
        self.layout.addLayout(row)

        self.fit_peaks = QCheckBox("Pseudo-Voigt 峰形拟合")
        self.fit_peaks.setChecked(True)
        self.instrument_mode = QComboBox()
        self.instrument_mode.addItem("仪器展宽：不校正", "none")
        self.instrument_mode.addItem("常数 FWHM", "constant")
        self.instrument_mode.addItem("CSV 曲线", "csv")
        self.instrument_fwhm = QDoubleSpinBox()
        self.instrument_fwhm.setRange(0.0, 10.0)
        self.instrument_fwhm.setDecimals(4)
        self.instrument_fwhm.setSuffix(" °")
        self.instrument_file = QLineEdit()
        self.instrument_file.setPlaceholderText("2θ,FWHM 的两列 CSV（仅 CSV 模式）")
        instrument_button = QPushButton("选择…")
        instrument_button.clicked.connect(self.choose_instrument_file)
        self.instrument_mode.currentIndexChanged.connect(self._toggle_instrument)
        row = QHBoxLayout()
        row.addWidget(self.fit_peaks)
        row.addWidget(self.instrument_mode)
        row.addWidget(QLabel("常数"))
        row.addWidget(self.instrument_fwhm)
        row.addWidget(self.instrument_file, 1)
        row.addWidget(instrument_button)
        self.layout.addLayout(row)
        self._toggle_instrument()

        self.background = QComboBox()
        self.background.addItem("不扣除背景", "none")
        self.background.addItem("左右高角线性背景", "linear")
        self.left_low = self._window_spin(10.0)
        self.left_high = self._window_spin(20.0)
        self.right_low = self._window_spin(70.0)
        self.right_high = self._window_spin(80.0)
        self.background.currentIndexChanged.connect(self._toggle_background)
        row = QHBoxLayout()
        row.addWidget(QLabel("背景"))
        row.addWidget(self.background)
        row.addWidget(QLabel("左窗口"))
        row.addWidget(self.left_low)
        row.addWidget(self.left_high)
        row.addWidget(QLabel("右窗口"))
        row.addWidget(self.right_low)
        row.addWidget(self.right_high)
        self._toggle_background()
        self.layout.addLayout(row)

        self.reference = QLineEdit()
        self.reference.setPlaceholderText("可选参考峰 CSV/XY（2θ，强度，可选 phase 列）")
        reference_button = QPushButton("选择…")
        reference_button.clicked.connect(self.choose_reference)
        self.match_tolerance = QDoubleSpinBox()
        self.match_tolerance.setRange(0.001, 5.0)
        self.match_tolerance.setDecimals(3)
        self.match_tolerance.setValue(0.2)
        self.match_tolerance.setSuffix(" °")
        self.start_button = QPushButton("开始 XRD 分析")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start_analysis)
        row = QHBoxLayout()
        row.addWidget(QLabel("参考相"))
        row.addWidget(self.reference, 1)
        row.addWidget(reference_button)
        row.addWidget(QLabel("匹配容差"))
        row.addWidget(self.match_tolerance)
        row.addWidget(self.start_button)
        self.layout.addLayout(row)

        self.plot = PlotCanvas()
        self.plot.set_placeholder("选择 XRD 文件并开始分析\n图谱与检测峰将在此显示")
        self.plot.preview_requested.connect(self.preview_figure)
        self.summary = QTextBrowser()
        self.summary.setMinimumWidth(300)
        self.summary.setPlainText("完成 XRD 分析后，这里显示检测峰、FWHM、d 间距、Scherrer 尺寸与匹配分数。")
        split = QSplitter()
        split.addWidget(self.plot)
        split.addWidget(self.summary)
        split.setSizes([800, 360])
        self.layout.addWidget(split, 1)

        self.peaks = QTableWidget(0, 9)
        self.peaks.setHorizontalHeaderLabels(["2θ (°)", "强度 (%)", "FWHM (°)", "拟合 FWHM (°)", "η",
                                              "d (Å)", "Scherrer (nm)", "R²", "拟合"])
        self.peaks.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.peaks.horizontalHeader().setStretchLastSection(True)
        self.peaks.setMaximumHeight(180)
        self.layout.addWidget(self.peaks)

        row = QHBoxLayout()
        self.save_button = QPushButton("保存当前图")
        self.save_button.clicked.connect(self.save_selected)
        self.save_all_button = QPushButton("导出全部图片")
        self.save_all_button.clicked.connect(self.save_all)
        self.report_button = QPushButton("导出 XRD 报告…")
        self.report_button.clicked.connect(self.save_report)
        self.open_button = QPushButton("打开结果目录")
        self.open_button.clicked.connect(self.open_output)
        for button in (self.save_button, self.save_all_button, self.report_button, self.open_button):
            row.addWidget(button)
        row.addStretch()
        self.layout.addLayout(row)

    @staticmethod
    def _window_spin(value):
        spin = QDoubleSpinBox()
        spin.setRange(-10.0, 180.0)
        spin.setDecimals(3)
        spin.setValue(value)
        spin.setSuffix(" °")
        return spin

    def _toggle_background(self):
        enabled = self.background.currentData() == "linear"
        for spin in (self.left_low, self.left_high, self.right_low, self.right_high):
            spin.setEnabled(enabled)

    def _toggle_instrument(self):
        mode = self.instrument_mode.currentData()
        self.instrument_fwhm.setEnabled(mode == "constant")
        self.instrument_file.setEnabled(mode == "csv")

    def choose_instrument_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择仪器展宽曲线", "", "展宽曲线 (*.csv *.txt *.xy);;所有文件 (*)")
        if path:
            self.instrument_file.setText(path)
            self.instrument_mode.setCurrentIndex(self.instrument_mode.findData("csv"))

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 XRD 原始文件", "",
            "XRD 数据 (*.csv *.txt *.xy *.dat *.raw);;Bruker RAW (*.raw *.txt);;所有文件 (*)")
        if path:
            self.file.setText(path)
            self.name.setText(Path(path).stem)
            self.load_columns()

    def choose_reference(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择参考峰文件", "", "参考峰 (*.csv *.txt *.xy *.dat);;所有文件 (*)")
        if path:
            self.reference.setText(path)

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output.text())
        if path:
            self.output.setText(path)

    def load_columns(self):
        path = self.file.text().strip()
        if not path:
            return
        try:
            preview = inspect_xrd_table(path)
        except Exception as error:
            self.show_error(f"读取列名失败：{error}")
            return
        two_theta, intensity = suggest_xrd_columns(preview["columns"])
        metadata = preview["metadata"]
        if metadata.get("wavelength_angstrom"):
            self.wavelength.setValue(float(metadata["wavelength_angstrom"]))
        for combo, suggested in ((self.two_theta_column, two_theta), (self.intensity_column, intensity)):
            current = combo.currentText().strip()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(preview["columns"])
            if suggested:
                combo.setCurrentText(suggested)
            elif current in preview["columns"]:
                combo.setCurrentText(current)
            combo.blockSignals(False)
        try:
            data = read_xrd(path, two_theta_column=self.two_theta_column.currentText().strip() or None,
                            intensity_column=self.intensity_column.currentText().strip() or None)
            low, high = float(data.frame["two_theta_deg"].min()), float(data.frame["two_theta_deg"].max())
            span = max(high - low, 1.0)
            self.left_low.setValue(low)
            self.left_high.setValue(low + span * .1)
            self.right_low.setValue(high - span * .1)
            self.right_high.setValue(high)
        except Exception:
            pass
        self.message.emit(f"读取到 {len(preview['columns'])} 列、{preview['rows']} 行；请确认 2θ 与强度列。")
        if metadata.get("raw4_text"):
            hint = ("Bruker RAW4 文本：已从文件头读取波长"
                    f"{metadata.get('wavelength_angstrom')} Å（{metadata.get('wavelength_source')}）。")
            if metadata.get("raw_binary"):
                hint += " 二进制 .raw 通过同名 .txt 转换文件读取。"
            self.message.emit(hint)

    def _config(self):
        path, name, output = self.file.text().strip(), self.name.text().strip(), self.output.text().strip()
        if not path or not name or not output:
            raise ValueError("请指定 XRD 文件、样品名称和输出目录。")
        if not Path(path).is_file():
            raise ValueError(f"原始文件不存在：{path}")
        reference = self.reference.text().strip() or None
        if reference and not Path(reference).is_file():
            raise ValueError(f"参考相文件不存在：{reference}")
        return XRDConfig(
            path=Path(path), name=name, output=Path(output),
            two_theta_column=self.two_theta_column.currentText().strip() or None,
            intensity_column=self.intensity_column.currentText().strip() or None,
            wavelength_angstrom=float(self.wavelength.value()), k_factor=float(self.k_factor.value()),
            background_mode=self.background.currentData(),
            background_left=(float(self.left_low.value()), float(self.left_high.value())),
            background_right=(float(self.right_low.value()), float(self.right_high.value())),
            min_prominence_relative=float(self.min_prominence.value()) / 100.0,
            min_distance_deg=float(self.min_distance.value()),
            smoothing_points=int(self.smoothing.currentData()),
            fit_peaks=self.fit_peaks.isChecked(),
            instrument_mode=self.instrument_mode.currentData(),
            instrument_fwhm_deg=float(self.instrument_fwhm.value()),
            instrument_file=Path(self.instrument_file.text().strip()) if self.instrument_file.text().strip() else None,
            reference_path=Path(reference) if reference else None,
            match_tolerance_deg=float(self.match_tolerance.value()),
            dpi=self.export_dpi, entry_point="gui_xrd")

    def start_analysis(self):
        try:
            config = self._config()
        except Exception as error:
            self.show_error(str(error))
            return
        self.badge.set_status("PENDING", "XRD 峰分析进行中；未做仪器展宽校正。")
        self.launch(lambda progress, cancelled: analyze_xrd_request(config, progress, cancelled),
                    self.analyzed)

    def analyzed(self, result):
        self.completed = result
        self._display(result)
        self.analysis_completed.emit(result)

    def _display(self, result):
        record, metrics = result["record"], result["metrics"]
        self.summary.setPlainText(xrd_summary_text(record, metrics))
        peaks = metrics.get("peaks") or []
        self.peaks.setRowCount(len(peaks))
        keys = ("center_deg", "relative_intensity_pct", "fwhm_deg", "fwhm_fit_deg", "eta",
                "d_angstrom", "crystallite_size_nm", "fit_r_squared")
        optional = {"fwhm_fit_deg", "eta", "fit_r_squared"}
        for row_index, peak in enumerate(peaks):
            for column_index, key in enumerate(keys):
                value = peak.get(key)
                text = "—" if value is None and key in optional else \
                    ("不可计算" if value is None else f"{float(value):.6g}")
                self.peaks.setItem(row_index, column_index, QTableWidgetItem(text))
            converged = peak.get("fit_converged")
            self.peaks.setItem(row_index, 8, QTableWidgetItem("是" if converged else "否（插值）"))
        self.plot.set_figures(result["figures"])
        if record.get("status") == "not_computable":
            self.badge.set_status("NOT_COMPUTABLE", "未检测到满足阈值的峰；详见警告。")
        else:
            self.badge.set_status("PENDING", "XRD 峰分析完成；外部参考核对仍待进行。")
        self.message.emit(f"XRD 分析完成：{result['directory']}")

    def preview_figure(self, key):
        if not self.completed or self.busy:
            return
        result = self.completed
        def operation(progress, cancelled):
            figure = xrd_figure(result, key, 100)
            plt.close(figure)
            return figure
        self.launch(operation, lambda figure: self.plot.install_preview(key, figure))

    def save_selected(self):
        if not self.completed:
            return
        key = self.plot.selector.currentData() or "xrd_pattern"
        result, dpi = self.completed, self.export_dpi
        self.save_plot(lambda: xrd_figure(result, key, dpi))

    def save_all(self):
        if not self.completed:
            return
        result, dpi = self.completed, self.export_dpi
        self.save_all_plots({key: (lambda k=key: xrd_figure(result, k, dpi)) for key in result["figures"]})

    def save_report(self):
        if not self.completed:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 XRD 报告", "xrd_report.docx",
                                              "Word (*.docx);;PDF (*.pdf)")
        if not path:
            return
        directory, dpi = self.completed["directory"], self.export_dpi
        from export.xrd_report import export_xrd_report

        def operation(progress, cancelled):
            progress(10, "生成 XRD 报告")
            return export_xrd_report(directory, path, formats=("docx", "pdf"), dpi=dpi)
        self.launch(operation, lambda files: self.message.emit(
            "XRD 报告已保存：" + "；".join(str(item) for item in files)))

    def open_completed_run(self, directory):
        if self.busy:
            self.message.emit("当前任务运行中，请稍后再载入 XRD 运行。")
            return False
        try:
            result = load_xrd_request(directory)
        except Exception as error:
            logging.getLogger("microwave.gui").exception("载入 XRD 运行失败")
            self.show_error(f"无法载入 XRD 运行：{error}")
            return False
        self.completed = result
        self.file.setText(result["record"].get("raw_file", ""))
        self.name.setText(result["record"].get("sample", ""))
        self._display(result)
        self.message.emit("已载入工作区登记的 XRD 运行；未重新计算。")
        return True
