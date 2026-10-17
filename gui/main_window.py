"""中文桌面主窗口；Phase 1 以外的导航明确显示未开放。"""

from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QListWidget, QStackedWidget, QLabel
from core import __version__
from gui.pages.home_page import HomePage
from gui.pages.single_sample_page import SingleSamplePage
from gui.pages.sparameter_page import SParameterPage
from gui.pages.comparison_page import ComparisonPage
from gui.pages.batch_page import BatchPage
from gui.pages.results_page import ResultsPage
from gui.pages.settings_page import SettingsPage
from gui.controllers.settings_controller import SettingsStore


class MainWindow(QMainWindow):
    def __init__(self, settings_store=None):
        super().__init__()
        self.setWindowTitle(f"微波吸收材料分析软件 · v{__version__} · GUI Phase 4")
        self.resize(1400, 900)
        self.setMinimumSize(1200, 750)
        self.setAcceptDrops(True)
        body = QWidget()
        layout = QHBoxLayout(body)
        self.navigation = QListWidget()
        self.navigation.addItems(["首页", "单样品分析", "S参数分析", "多样品比较", "批量分析", "结果查看", "设置"])
        self.navigation.setFixedWidth(170)
        self.stack = QStackedWidget()
        self.home = HomePage()
        self.single = SingleSamplePage()
        self.stack.addWidget(self.home)
        self.stack.addWidget(self.single)
        self.sparameters = SParameterPage()
        self.comparison = ComparisonPage()
        self.stack.addWidget(self.sparameters)
        self.stack.addWidget(self.comparison)
        self.batch = BatchPage()
        self.history = ResultsPage()
        self.stack.addWidget(self.batch)
        self.stack.addWidget(self.history)
        self.task_pages = [self.single, self.sparameters, self.comparison, self.batch, self.history]
        from gui.widgets.mapping_dialog import configure_mapping
        for page in (self.single,self.comparison,self.batch):
            page.parameters.mapping_button.clicked.connect(lambda checked=False,p=page:configure_mapping(p,p.parameters))
        for page in (self.comparison,self.batch):
            page.parameters.quick_preview.hide()
        self.single.analysis_completed.connect(self.sparameters.add_theory)
        self.single.analysis_completed.connect(lambda r: self.comparison.add_source(r["record"]["raw_file"], r["sample"].name))
        self.single.table.source_selected.connect(self.transfer_source)
        for page in self.task_pages:
            page.busy_changed.connect(self.update_task_lock)
            page.message.connect(self.statusBar().showMessage)
        self.settings_store = settings_store or SettingsStore()
        self.settings = SettingsPage()
        self.stack.addWidget(self.settings)
        self.settings.apply_requested.connect(self.save_settings)
        preferences, settings_warning = self.settings_store.load()
        self.apply_preferences(preferences)
        self.settings.message.setText(settings_warning)
        layout.addWidget(self.navigation)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(body)
        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.home.navigate.connect(self.navigation.setCurrentRow)
        self.single.message.connect(self.statusBar().showMessage)
        self.navigation.setCurrentRow(0)
        self.statusBar().showMessage("就绪 · 缺失数据插值 OFF · 真实数据验证 PENDING")
        if settings_warning:
            self.statusBar().showMessage(settings_warning)
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #f5f7fa; color: #25364a; }
            QLineEdit, QDoubleSpinBox, QComboBox, QTreeWidget, QTextBrowser { background: white; }
            QPushButton { background: #e5edf5; border: 1px solid #bccbd9; border-radius: 4px; padding: 7px; }
            QPushButton:hover { background: #d6e5f3; }
            QPushButton:disabled { color: #8796a4; background: #edf0f3; }
            QListWidget { background: #e9eef4; border: none; font-size: 15px; }
            QListWidget::item { padding: 17px 10px; }
            QListWidget::item:selected { background: #cedeee; color: #173e65; }
            QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox { padding: 4px; border: 1px solid #bccbd9; border-radius: 3px; }
            QTabWidget::pane { border: 1px solid #d4dde6; }
            QHeaderView::section { background: #e9eef4; padding: 5px; border: none; }
        """)

    def apply_preferences(self, values):
        self.settings.populate(values)
        for page in (self.single, self.comparison, self.batch):
            page.parameters.apply_defaults(values)
        self.sparameters.output.setText(values["output"])
        for page in self.task_pages:
            page.export_dpi = values["dpi"]
            page.figure_format = values["figure_format"]

    def save_settings(self, values):
        if any(page.busy for page in self.task_pages):
            self.settings.message.setText("任务运行中，结束后可应用默认设置。")
            return
        try:
            saved = self.settings_store.save(values)
            self.apply_preferences(saved)
            self.settings.message.setText("已保存并应用；参数修改不自动计算。更改单位后请重新导入检查。")
        except Exception as error:
            import logging
            logging.getLogger("microwave.gui").exception("设置保存失败")
            self.settings.message.setText(f"保存失败，参数未应用：{error}")

    def dragEnterEvent(self, event):
        """只接收本地文件 URL；分析运行中不接受新的拖入。"""
        if not any(p.busy for p in self.task_pages) and event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        """拖拽复用与文件对话框相同的导入路径。"""
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths and not any(p.busy for p in self.task_pages):
            self.navigation.setCurrentRow(1)
            self.single.import_paths(paths)
            event.acceptProposedAction()

    def closeEvent(self, event):
        """不销毁运行中的 QThread；先请求取消，让用户在任务结束后关闭。"""
        if any(p.busy for p in self.task_pages):
            for page in self.task_pages:
                if page.busy:
                    page.cancel()
            self.statusBar().showMessage("正在安全结束后台任务；结束后可再次关闭窗口。")
            event.ignore()
        else:
            event.accept()

    def update_task_lock(self, *_):
        """跨页面串行运行 pyplot 任务，其他页面可导航但不能并发操作。"""
        active = next((p for p in self.task_pages if p.busy), None)
        for page in self.task_pages:
            page.setEnabled(active is None or page is active)
        self.settings.setEnabled(active is None)

    def transfer_source(self, info):
        """已选 SDAT 传给独立页面；不自动把它送入材料计算。"""
        if info and info["format"] == ".sdat":
            self.sparameters.file.setText(str(info["path"]))
            self.sparameters.name.setText(info["sample"])
