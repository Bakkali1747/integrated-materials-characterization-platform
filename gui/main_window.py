"""中文桌面主窗口；Phase 1 以外的导航明确显示未开放。"""

from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QListWidget, QStackedWidget, QLabel
from core import __version__
from gui.pages.home_page import HomePage
from gui.pages.single_sample_page import SingleSamplePage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"微波吸收材料分析软件 · v{__version__} · GUI Phase 1")
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
        for title, phase in [("S参数分析", 2), ("多样品比较", 2), ("批量分析", 3), ("历史结果查看", 3), ("完整设置", 4)]:
            label = QLabel(f"{title}\n将在 GUI Phase {phase} 开放。\n本阶段请使用单样品页面；现有 CLI 功能继续可用。")
            label.setMargin(30)
            self.stack.addWidget(label)
        layout.addWidget(self.navigation)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(body)
        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.home.navigate.connect(self.navigation.setCurrentRow)
        self.single.message.connect(self.statusBar().showMessage)
        self.navigation.setCurrentRow(0)
        self.statusBar().showMessage("就绪 · 缺失数据插值 OFF · 真实数据验证 PENDING")
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #f5f7fa; color: #25364a; }
            QLineEdit, QDoubleSpinBox, QComboBox, QTreeWidget, QTextBrowser { background: white; }
            QPushButton { background: #e5edf5; border: 1px solid #bccbd9; border-radius: 4px; padding: 7px; }
            QPushButton:hover { background: #d6e5f3; }
            QPushButton:disabled { color: #8796a4; background: #edf0f3; }
            QListWidget { background: #e9eef4; border: none; font-size: 15px; }
            QListWidget::item { padding: 17px 10px; }
            QListWidget::item:selected { background: #cedeee; color: #173e65; }
        """)

    def dragEnterEvent(self, event):
        """只接收本地文件 URL；分析运行中不接受新的拖入。"""
        if not self.single.busy and event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        """拖拽复用与文件对话框相同的导入路径。"""
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths and not self.single.busy:
            self.navigation.setCurrentRow(1)
            self.single.import_paths(paths)
            event.acceptProposedAction()

    def closeEvent(self, event):
        """不销毁运行中的 QThread；先请求取消，让用户在任务结束后关闭。"""
        if self.single.busy:
            self.single.cancel()
            self.statusBar().showMessage("正在安全结束后台任务；结束后可再次关闭窗口。")
            event.ignore()
        else:
            event.accept()
