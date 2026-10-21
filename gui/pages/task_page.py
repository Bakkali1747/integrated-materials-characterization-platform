"""Phase 2 页面共用的后台任务及导出生命周期。"""
from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from export.origin_export import save_figure_bundle
from export.provenance import figure_provenance
from gui.controllers.analysis_controller import Cancelled
from gui.workers.analysis_worker import AnalysisWorker


class TaskPage(QWidget):
    message = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, title):
        super().__init__()
        self.worker = None
        self.completed = None
        self.export_dpi = 600
        self.figure_format = "png"
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.outer.setSpacing(10)
        self.heading = QLabel(title)
        self.heading.setObjectName("pageTitle")
        self.outer.addWidget(self.heading)
        self.body = QWidget()
        self.layout = QVBoxLayout(self.body)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.outer.addWidget(self.body, 1)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #a03127;")
        self.outer.addWidget(self.error)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.outer.addWidget(self.progress)
        self.cancel_button = QPushButton("取消（当前步骤结束后生效）")
        self.cancel_button.setObjectName("ghostButton")
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        self.outer.addWidget(self.cancel_button)
        self.last_data_directory = None
        self.data_button = QPushButton("打开最近导出的图片数据目录")
        self.data_button.setObjectName("ghostButton")
        self.data_button.setVisible(False)
        self.data_button.setEnabled(False)
        self.data_button.clicked.connect(self.open_export_data)
        self.outer.addWidget(self.data_button)

    def text(self):
        """返回页面标题，供导航和辅助检查读取。"""
        return self.heading.text()

    @property
    def busy(self):
        return self.worker is not None

    def launch(self, operation, callback):
        """后台执行，参数必须预先快照，禁止后台读取 Qt 控件。"""
        if self.busy:
            return
        self.error.clear()
        self.progress.setValue(0)
        self.worker = AnalysisWorker(operation, self)
        self.worker.progress.connect(self.on_progress)
        self.worker.succeeded.connect(callback)
        self.worker.failed.connect(self.show_error)
        self.worker.cancelled.connect(self.show_cancelled)
        self.worker.finished.connect(self.finished)
        self.body.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.progress.setVisible(True)
        self.busy_changed.emit(True)
        self.worker.start()

    def on_progress(self, value, text):
        self.progress.setValue(value)
        self.message.emit(text)

    def show_error(self, text):
        self.error.setStyleSheet("color: #a03127;")
        self.error.setText(text)
        self.message.emit(text.splitlines()[0])

    def show_cancelled(self, text="已取消；已生成的文件保留。"):
        """主动取消是中性结果，不用红色错误呈现。"""
        self.error.setStyleSheet("color: #5b6b7c;")
        self.error.setText(text)
        self.message.emit("已取消")

    def finished(self):
        worker, self.worker = self.worker, None
        worker.deleteLater()
        self.body.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setVisible(False)
        self.progress.setVisible(False)
        self.busy_changed.emit(False)

    def cancel(self):
        if self.worker:
            self.worker.requestInterruption()
            self.cancel_button.setEnabled(False)

    def open_output(self):
        if self.completed:
            path = self.completed["directory"]
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
                self.show_error(f"无法打开 {path}")

    def save_plot(self, builder):
        """输入只依赖结果快照的绘图函数；后台原子保存，不触碰 Qt canvas。"""
        if not self.completed or self.busy:
            return
        dpi, extension = self.export_dpi, self.figure_format
        provenance = figure_provenance(self.completed.get("record"), dpi=dpi)
        filters = [f"{fmt.upper()} (*.{fmt})" for fmt in (extension, *[f for f in ("png","tiff","pdf","svg") if f != extension])]
        path, selected = QFileDialog.getSaveFileName(self, f"保存图片（{dpi} dpi）", f"figure.{extension}", ";;".join(filters))
        if not path:
            return
        path = Path(path)
        if not path.suffix:
            path = path.with_suffix("." + selected.split()[0].lower())
        if path.suffix.lower() not in {".png", ".tiff", ".tif", ".pdf", ".svg"}:
            self.show_error("不支持的图片格式。")
            return
        if path.resolve().is_relative_to(self.completed["directory"].resolve()):
            self.show_error("请另选位置，保留分析目录的原始追溯产物。")
            return

        def operation(progress, cancelled):
            from plotting.style import plt
            if cancelled():
                raise Cancelled("导出已取消")
            fig = builder()
            try:
                save_figure_bundle(fig, path, dpi=dpi, bbox_inches="tight", cancelled=cancelled,
                                   cancel_error=Cancelled, provenance=provenance)
                return path
            finally:
                plt.close(fig)
        def saved(p):
            self.last_data_directory=p.with_name(p.name+".data")
            self.data_button.setVisible(True)
            self.data_button.setEnabled(True)
            self.message.emit(f"图片与独立数据已保存：{p}")
        self.launch(operation, saved)

    def open_export_data(self):
        path=self.last_data_directory
        if path is not None and path.is_dir():
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))): self.show_error(f"无法打开：{path}")
        else: self.show_error("最近导出的数据目录不存在。")

    def save_all_plots(self, builders):
        if not self.completed or self.busy:
            return
        output = QFileDialog.getExistingDirectory(self, "导出全部图片（创建独立子目录）")
        if not output:
            return
        from gui.controllers.export_controller import export_all_builders
        source, extension, dpi = self.completed["directory"], self.figure_format, self.export_dpi
        self.launch(lambda p,c: export_all_builders(builders,source,output,extension,dpi,p,c),
                    lambda path:self.message.emit(f"全部图片已保存：{path}"))
