"""Phase 2 页面共用的后台任务及导出生命周期。"""
from pathlib import Path
import os
import tempfile
from PySide6.QtCore import Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QProgressBar, QFileDialog
from gui.workers.analysis_worker import AnalysisWorker
from gui.controllers.analysis_controller import Cancelled


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
        self.heading = QLabel(title)
        self.outer.addWidget(self.heading)
        self.body = QWidget()
        self.layout = QVBoxLayout(self.body)
        self.outer.addWidget(self.body, 1)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #a03127;")
        self.outer.addWidget(self.error)
        self.progress = QProgressBar()
        self.outer.addWidget(self.progress)
        self.cancel_button = QPushButton("取消（当前步骤结束后生效）")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        self.outer.addWidget(self.cancel_button)

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
        self.worker.cancelled.connect(self.show_error)
        self.worker.finished.connect(self.finished)
        self.body.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.busy_changed.emit(True)
        self.worker.start()

    def on_progress(self, value, text):
        self.progress.setValue(value)
        self.message.emit(text)

    def show_error(self, text):
        self.error.setText(text)
        self.message.emit(text.splitlines()[0])

    def finished(self):
        worker, self.worker = self.worker, None
        worker.deleteLater()
        self.body.setEnabled(True)
        self.cancel_button.setEnabled(False)
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
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, suffix=path.suffix, delete=False) as handle:
                    temporary = Path(handle.name)
                fig.savefig(temporary, dpi=dpi, bbox_inches="tight")
                if cancelled():
                    raise Cancelled("导出已取消，未改变目标")
                os.replace(temporary, path)
                return path
            finally:
                plt.close(fig)
                if temporary:
                    temporary.unlink(missing_ok=True)
        self.launch(operation, lambda p: self.message.emit(f"已保存：{p}"))

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
