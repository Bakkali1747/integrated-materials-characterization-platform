"""单样品操作页面；任务期间锁定输入，结果绑定实际分析快照。"""

from pathlib import Path
import logging
from PySide6.QtCore import Signal, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                               QSplitter, QTextBrowser, QProgressBar, QScrollArea, QFileDialog)
from gui.controllers.analysis_controller import analyze_request, inspect_file, Cancelled, SUPPORTED
from gui.controllers.export_controller import export_figure
from gui.workers.analysis_worker import AnalysisWorker
from gui.widgets.file_selector import FileSelector
from gui.widgets.sample_table import SampleTable
from gui.widgets.parameter_panel import ParameterPanel
from gui.widgets.plot_canvas import PlotCanvas
from gui.widgets.status_badge import StatusBadge


class SingleSamplePage(QWidget):
    message = Signal(str)
    analysis_started = Signal(object)
    analysis_completed = Signal(object)
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.selected = None
        self.completed = None
        self.export_dpi = 600
        self.figure_format = "png"
        layout = QVBoxLayout(self)
        self.badge = StatusBadge("PENDING", "MEMP 可计算 / 待商业软件验证；虚部定义尚未交叉确认。所有真实结果待验证。")
        layout.addWidget(self.badge)
        self.files = FileSelector()
        layout.addWidget(self.files)
        self.table = SampleTable()
        self.table.setMaximumHeight(190)
        layout.addWidget(self.table)
        self.files.files_selected.connect(self.import_paths)
        self.table.source_selected.connect(self.select_source)
        split = QSplitter()
        self.parameters = ParameterPanel()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.parameters)
        scroll.setMinimumWidth(295)
        self.plot = PlotCanvas()
        self.summary = QTextBrowser()
        self.summary.setMinimumWidth(245)
        self.summary.setPlainText("尚无分析结果。\n\n原始点保持不变；缺失数据不插值。")
        split.addWidget(scroll)
        split.addWidget(self.plot)
        split.addWidget(self.summary)
        split.setSizes([315, 590, 270])
        layout.addWidget(split, 1)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #a03127;")
        self.error.hide()
        layout.addWidget(self.error)
        self.source_label = QLabel("文件来源：未选择")
        self.source_label.setWordWrap(True)
        layout.addWidget(self.source_label)
        buttons = QHBoxLayout()
        self.start_button = QPushButton("开始分析")
        self.cancel_button = QPushButton("取消（当前步骤结束后生效）")
        self.open_button = QPushButton("打开结果文件夹")
        self.save_button = QPushButton("保存当前图片…")
        self.save_all_button = QPushButton("导出全部图片…")
        self.save_all_button.clicked.connect(self.save_all_figures)
        self.save_all_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.save_button.setEnabled(False)
        for button in (self.start_button, self.cancel_button, self.open_button, self.save_button, self.save_all_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        self.start_button.clicked.connect(self.start_analysis)
        self.cancel_button.clicked.connect(self.cancel)
        self.open_button.clicked.connect(self.open_output)
        self.save_button.clicked.connect(self.save_figure)

    @property
    def busy(self):
        return self.worker is not None

    def _launch(self, operation, on_success):
        """统一生命周期；线程结束前禁止重入及删除窗口。"""
        self.error.hide()
        self.worker = AnalysisWorker(operation, self)
        self.worker.progress.connect(self.on_progress)
        self.worker.succeeded.connect(on_success)
        self.worker.failed.connect(self.show_error)
        self.worker.cancelled.connect(self.show_error)
        self.worker.finished.connect(self._finished)
        self._set_busy(True)
        self.progress.setValue(0)
        self.worker.start()

    def _set_busy(self, busy):
        """锁定任务快照相关控件；保留窗口导航和取消响应。"""
        for widget in (self.files, self.table, self.parameters, self.plot):
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        ready = self.selected is not None and self.selected["status"] != "FAIL" and self.selected["format"] != ".sdat"
        self.start_button.setEnabled(not busy and ready)
        self.open_button.setEnabled(not busy and self.completed is not None)
        self.save_button.setEnabled(not busy and self.completed is not None)
        self.save_all_button.setEnabled(not busy and self.completed is not None)
        self.busy_changed.emit(busy)

    def _finished(self):
        """Qt 线程真正结束后清理对象，解除输入锁定。"""
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        self._set_busy(False)

    def on_progress(self, percent, text):
        self.progress.setValue(percent)
        self.message.emit(text)

    def cancel(self):
        """请求协作式停止；不 terminate 线程、不删除既有结果。"""
        if self.worker:
            self.worker.requestInterruption()
            self.cancel_button.setEnabled(False)
            self.message.emit("已请求取消，等待当前步骤完整结束…")

    def import_paths(self, paths):
        """快照解析选项，在后台扫描/解析；单文件失败不阻止其他导入。"""
        if self.busy:
            self.message.emit("当前任务运行中，请完成或取消后再导入。")
            return
        try:
            options = self.parameters.parser_options()
        except Exception as error:
            logging.getLogger("microwave.gui").exception("解析配置无效")
            self.show_error(f"解析配置无效：{error}")
            return

        def operation(progress, cancelled):
            sources = []
            for value in paths:
                path = Path(value)
                if path.is_dir():
                    sources.extend(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED)
                else:
                    sources.append(path)
            sources = list(dict.fromkeys(p.resolve() for p in sources))
            result = []
            for index, path in enumerate(sources):
                if cancelled():
                    raise Cancelled("导入已取消；已有列表保留。")
                parser_options = dict(options)
                if path.suffix.lower() == ".memp":
                    parser_options.pop("column_map", None)
                    parser_options.pop("frequency_unit", None)
                result.append(inspect_file(path, parser_options))
                progress(round(100 * (index + 1) / len(sources)), f"读取：{path.name}")
            return result

        self._launch(operation, self._imported)

    def _imported(self, infos):
        """填充文件摘要；优先选中可用于单样品分析的 ε/μ 来源。"""
        first = None
        for info in infos:
            item = self.table.add_source(info)
            if first is None or (first.data(0, Qt.ItemDataRole.UserRole)["format"] == ".sdat" and info["format"] != ".sdat"):
                first = item
        if first:
            self.table.setCurrentItem(first)
            self.select_source(first.data(0, Qt.ItemDataRole.UserRole))
        else:
            self.show_error("所选目录未发现支持的文件。只扫描当前目录，不递归子目录。")
        self.message.emit(f"导入完成：{len(infos)} 个文件")

    def select_source(self, info):
        """更新来源提示；既有摘要仍明确属于上一次已完成运行。"""
        self.selected = info
        if info is None:
            self.source_label.setText("文件来源：请选择一个文件子项")
        else:
            self.parameters.name.setText(info["sample"])
            self.source_label.setText(f"文件来源：{info['path']}")
            if info["format"] == ".sdat":
                self.badge.set_status(info["status"], "Measured S Parameters；S21/S12 顺序待厂商确认。请切换左侧 S 参数分析页面。")
            else:
                self.badge.set_status(info["status"], "Calculated RL from ε/μ；虚部定义 / 商业软件定量验证 PENDING。")
            if info.get("error"):
                self.show_error(f"样品：{info['sample']}\n解析失败：{info['error']}\n请检查原始文件和列映射；调整后重新导入。")
            else:
                self.error.hide()
        self._set_busy(self.busy)

    def start_analysis(self):
        """用户显式触发一次分析，不监听参数值变化来计算。"""
        if self.busy or not self.selected or self.selected["format"] == ".sdat" or self.selected["status"] == "FAIL":
            return
        try:
            request = self.parameters.request(self.selected["path"])
        except Exception as error:
            logging.getLogger("microwave.gui").exception("参数输入无效")
            self.show_error(f"参数输入无效：{error}")
            return
        self.analysis_started.emit(request)
        self._launch(lambda progress, cancelled: analyze_request(request, progress, cancelled), self._analyzed)

    def _analyzed(self, result):
        """展示核心摘要，保留所有并列最小值和分离频带。"""
        self.completed = result
        self.plot.set_figures(result["figures"])
        record, summary = result["record"], result["summary"]
        lines = ["[COMPUTED] 已完成的分析快照", f"样品：{record['sample']}",
                 "验证状态：PENDING（真实结果待验证）", f"来源：{record['raw_file']}",
                 f"Parser：{record['parser_version']}", f"频率：{record['frequency_range_ghz']} GHz",
                 f"数据点：{record['frequency_points']}", f"扫描厚度：{record['thickness_range_mm']} mm",
                 f"厚度步长：{record['thickness_step_mm']:g} mm", "", "网格 RLmin（全部并列点）："]
        for p in summary["global_minima"]:
            lines.append(f"{p['rl_min_db']:.6g} dB / {p['frequency_ghz']:g} GHz / {p['thickness_mm']:g} mm")
        for title, bands in [("Maximum EAB（−10 dB）", summary["standard_eab"]),
                             (f"指定阈值连续带宽（{record['rl_threshold_db']:g} dB）", summary["selected_threshold_bandwidth"])]:
            lines += ["", f"{title}：{bands['maximum_bandwidth_ghz']:.6g} GHz"]
            for entry in bands["best_thicknesses"]:
                lines.append(f"厚度：{entry['thickness_mm']:g} mm")
                for b in entry["widest_bands"]:
                    lines.append(f"频段：{b['start_ghz']:.6g}–{b['end_ghz']:.6g} GHz")
        lines += ["", f"指定曲线厚度：{record['configuration']['curve_thickness_mm']:g} mm",
                  f"当前厚度 RLmin：{summary['curve_minima'][0]['rl_min_db']:.6g} dB",
                  f"当前厚度 Maximum continuous EAB：{summary['curve_standard_eab']['maximum_continuous_bandwidth_ghz']:.6g} GHz"]
        for i, band in enumerate(summary["curve_standard_eab"]["bands"], 1):
            lines.append(f"Band {i}：{band['start_ghz']:.6g}–{band['end_ghz']:.6g} GHz")
        if not summary["curve_standard_eab"]["bands"]:
            lines.append("当前厚度没有满足 −10 dB 的频段。")
        lines += ["不连续频段不累加为 EAB。", "", "警告：", *record["warnings"], "", f"结果目录：{result['directory']}"]
        lines += record.get("phase2", {}).get("notes", [])
        from gui.controllers.quality_controller import quality_text
        self.summary.setPlainText(quality_text(record) + "\n\n" + "\n".join(lines))
        self.message.emit("分析完成；结果待外部验证。")
        self.analysis_completed.emit(result)

    def show_error(self, text):
        self.error.setText(text)
        self.error.show()
        self.message.emit(text.splitlines()[0])

    def open_output(self):
        """打开已完成运行目录，而非当前尚未运行的输出输入框。"""
        if self.completed:
            path = self.completed["directory"]
            if not path.is_dir() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
                self.show_error(f"无法打开结果目录：{path}")

    def save_figure(self):
        """保存 PNG/TIFF/PDF/SVG，默认 600 dpi；绘制与磁盘写入移至后台。"""
        if self.busy or self.plot.current_figure() is None:
            return
        dpi, extension = self.export_dpi, self.figure_format
        filters = [f"{fmt.upper()} (*.{fmt})" for fmt in (extension, *[f for f in ("png","tiff","pdf","svg") if f != extension])]
        path, selected = QFileDialog.getSaveFileName(self, f"保存当前图片（{dpi} dpi）", f"figure.{extension}", ";;".join(filters))
        if not path:
            return
        path = Path(path)
        if not path.suffix:
            path = path.with_suffix({"PNG": ".png", "TIFF": ".tiff", "PDF": ".pdf", "SVG": ".svg"}[selected.split()[0]])
        if path.suffix.lower() not in {".png", ".tiff", ".tif", ".pdf", ".svg"}:
            self.show_error("图片格式仅支持 PNG / TIFF / PDF / SVG。")
            return
        # 不覆盖分析产物，避免使既有来源哈希失效。
        if path.resolve().is_relative_to(self.completed["directory"].resolve()):
            self.show_error("请另选导出位置，分析运行目录中的追溯产物保持不变。")
            return
        completed, key = self.completed, self.plot.selector.currentData()
        self._launch(lambda progress, cancelled: export_figure(completed, key, path, progress, cancelled, dpi=dpi),
                     lambda saved: self.message.emit(f"图片已保存：{saved}"))

    def save_all_figures(self):
        if self.busy or not self.completed:
            return
        output = QFileDialog.getExistingDirectory(self,"导出全部图片（创建独立子目录）")
        if not output:
            return
        from gui.controllers.export_controller import export_all_builders
        from gui.controllers.science_figures import make_figure
        from plotting.style import PlotStyle
        result, dpi, extension = self.completed, self.export_dpi, self.figure_format
        def builder(key):
            figure = make_figure(result,key,PlotStyle(dpi=dpi))
            return figure
        builders = {key:lambda k=key:builder(k) for key in result["figures"]}
        self._launch(lambda p,c:export_all_builders(builders,result["directory"],output,extension,dpi,p,c),
                     lambda path:self.message.emit(f"全部图片已保存：{path}"))
