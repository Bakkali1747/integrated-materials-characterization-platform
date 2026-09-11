"""历史快照与保存图片浏览，不重新计算。"""
import json
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QPushButton, QComboBox, QTextBrowser, QLabel, QSplitter, QScrollArea, QFileDialog, QTabWidget
from gui.widgets.image_view import ImageView
from gui.pages.task_page import TaskPage
from gui.controllers.history_controller import discover_history, load_history, read_figure
from gui.controllers.quality_controller import quality_text


class ResultsPage(TaskPage):
    def __init__(self):
        super().__init__("历史结果 · 只读已保存产物，不重新计算")
        button = QPushButton("打开历史结果目录"); button.clicked.connect(self.choose_folder); self.layout.addWidget(button)
        self.runs = QComboBox(); self.runs.activated.connect(self.load_selected); self.layout.addWidget(self.runs)
        self.figures = QComboBox(); self.figures.activated.connect(self.load_image); self.layout.addWidget(self.figures)
        split = QSplitter()
        tabs = QTabWidget()
        self.overview = QTextBrowser(); tabs.addTab(self.overview,"摘要 / QC")
        self.metadata = QTextBrowser(); tabs.addTab(self.metadata,"完整记录")
        self.integrity = QTextBrowser(); tabs.addTab(self.integrity,"产物核对")
        split.addWidget(tabs)
        self.image = ImageView()
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(self.image); split.addWidget(scroll)
        split.setSizes([420, 700]); self.layout.addWidget(split, 1)
        button = QPushButton("打开结果文件夹"); button.clicked.connect(self.open_output); self.layout.addWidget(button)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择 output / 样品 / 运行目录")
        if folder:
            self.scan(folder)

    def scan(self, folder):
        self.launch(lambda p,c: discover_history(folder,p,c), self.discovered)

    def discovered(self, paths):
        self.runs.clear()
        for path in paths:
            self.runs.addItem(str(path.parent), path)
        self.metadata.setPlainText(f"找到 {len(paths)} 份记录；从列表选择运行以读取。")
        self.overview.setPlainText(self.metadata.toPlainText())

    def load_selected(self, *_):
        path = self.runs.currentData()
        if path:
            self.launch(lambda p,c: load_history(path,p,c), self.loaded)

    def loaded(self, result):
        self.completed = result; self.image.clear(); self.figures.clear()
        for path in result["figures"]:
            self.figures.addItem(str(path.relative_to(result["directory"])), path)
        checks = result["checks"]
        integrity = "无产物哈希；完整性未核对" if not checks else f"产物哈希：{sum(s=='PASS' for _,s in checks)}/{len(checks)} 匹配"
        failures = [(name,state) for name,state in checks if state != "PASS"]
        self.metadata.setPlainText(f"运行状态：{result['record'].get('status','unknown')}\n" + integrity + "\n" + json.dumps(failures, ensure_ascii=False) + "\n" + quality_text(result["record"]) + "\n\n摘要：\n" + json.dumps(result["summaries"], ensure_ascii=False, indent=2) + "\n\n完整记录：\n" + json.dumps(result["record"], ensure_ascii=False, indent=2))
        record = result["record"]
        self.overview.setPlainText(f"样品：{record.get('sample','批量 / 比较')}\n状态：{record.get('status','unknown')}\n时间：{record.get('analysis_date','未记录')}\n软件版本：{record.get('software_version','未记录')}\n{integrity}\n\n" + quality_text(record) + "\n\n" + "\n".join(f"{name}\n{text}" for name,text in result["summaries"].items()))
        self.integrity.setPlainText(integrity + "\n\n" + "\n".join(f"{state}  {name}" for name,state in checks))
        if result.get("preview"):
            self.show_image(result["preview"])

    def load_image(self, *_):
        if self.completed and self.figures.currentData():
            directory, path = self.completed["directory"], self.figures.currentData()
            self.launch(lambda p,c: read_figure(directory,path,c), self.show_image)

    def show_image(self, data):
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self.show_error("图片无法解码；原始文件保留。")
        else:
            self.image.set_image(pixmap)
