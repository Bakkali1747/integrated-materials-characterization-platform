from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from gui.controllers.science_figures import NAMES


class ScientificToolbar(NavigationToolbar2QT):
    """保留导航，保存统一走后台导出，避免工具栏绕过追溯与 DPI 规则。"""
    toolitems = tuple(item for item in NavigationToolbar2QT.toolitems if item[0] != "Save")


class PlotCanvas(QWidget):
    """嵌入已有 Figure；不含计算公式、不弹出独立绘图窗口。"""

    preview_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.selector = QComboBox()
        self.layout.addWidget(self.selector)
        self.placeholder = QLabel("导入 ε/μ 数据并点击开始分析\n图形将在此显示")
        self.layout.addWidget(self.placeholder)
        self.figures, self.canvas, self.toolbar = {}, None, None
        self.selector.currentIndexChanged.connect(self.show_selected)

    def set_placeholder(self, text):
        """设置空图区域提示文字，不触发任何计算。"""
        self.placeholder.setText(text)

    def set_figures(self, figures):
        """输入后台完成的 Figure 集合；只在主线程连接 Qt canvas。"""
        self.selector.blockSignals(True)
        self.selector.clear()
        self.figures = figures
        names = NAMES
        for key in figures:
            self.selector.addItem(names.get(key, key), key)
        self.selector.blockSignals(False)
        self.show_selected()

    def show_selected(self, *_):
        """切换展示已有结果；不重新计算、不重新生成 Figure。"""
        for widget in (self.toolbar, self.canvas):
            if widget:
                self.layout.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()
        self.canvas = self.toolbar = None
        figure = self.current_figure()
        self.placeholder.setVisible(figure is None)
        if figure is not None:
            self.canvas = FigureCanvasQTAgg(figure)
            self.toolbar = ScientificToolbar(self.canvas, self)
            self.layout.addWidget(self.toolbar)
            self.layout.addWidget(self.canvas, 1)
            self.canvas.draw_idle()
        elif self.selector.currentData() in self.figures:
            self.placeholder.setText("此图按需生成；正在准备预览…")
            self.preview_requested.emit(self.selector.currentData())

    def install_preview(self, key, figure):
        self.figures[key] = figure
        if self.selector.currentData() == key:
            self.show_selected()

    def current_figure(self):
        """返回当前图，供独立导出任务使用。"""
        return self.figures.get(self.selector.currentData())
