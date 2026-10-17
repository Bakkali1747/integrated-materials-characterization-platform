"""历史快照与保存图片浏览，不重新计算。"""
import json
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QPushButton, QComboBox, QTextBrowser, QLabel, QSplitter, QScrollArea, QFileDialog, QTabWidget, QLineEdit
from gui.widgets.image_view import ImageView
from gui.pages.task_page import TaskPage
from gui.controllers.history_controller import history_index, load_history, read_figure
from gui.controllers.quality_controller import quality_text


class ResultsPage(TaskPage):
    def __init__(self):
        super().__init__("历史结果 · 只读已保存产物，不重新计算")
        button = QPushButton("打开历史结果目录"); button.clicked.connect(self.choose_folder); self.layout.addWidget(button)
        self.entries=[]
        self.search=QLineEdit(); self.search.setPlaceholderText("筛选样品、日期（如 2026-10）、参数或路径")
        self.search.textChanged.connect(self.filter_runs); self.layout.addWidget(self.search)
        self.status_filter=QComboBox(); self.status_filter.addItems(["全部","success","failed","cancelled","partial_failure","invalid"])
        self.status_filter.currentTextChanged.connect(self.filter_runs); self.layout.addWidget(self.status_filter)
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
        self.verify_button=QPushButton("核验当前运行的全部产物（SHA-256）")
        self.verify_button.clicked.connect(self.verify_selected); self.layout.addWidget(self.verify_button)
        data_button=QPushButton("打开当前历史图片的数据目录")
        data_button.clicked.connect(self.open_image_data); self.layout.addWidget(data_button)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择 output / 样品 / 运行目录")
        if folder:
            self.scan(folder)

    def scan(self, folder):
        self.launch(lambda p,c: history_index(folder,p,c), self.discovered)

    def discovered(self, paths):
        self.entries=[p if isinstance(p,dict) else dict(path=p,label=str(p.parent),search=str(p),status="unknown") for p in paths]
        self.filter_runs()
        self.metadata.setPlainText(f"找到 {len(paths)} 份记录；从列表选择运行以读取。")
        self.overview.setPlainText(self.metadata.toPlainText())

    def filter_runs(self,*_):
        self.runs.clear()
        query=self.search.text().casefold().split(); state=self.status_filter.currentText()
        for entry in self.entries:
            if (state=="全部" or state==entry["status"]) and all(word in entry["search"].casefold() for word in query):
                self.runs.addItem(entry["label"],entry["path"])

    def verify_selected(self):
        if self.completed:
            path=self.completed["record_path"]
            self.launch(lambda p,c:load_history(path,p,c,verify=True),self.loaded)

    def open_image_data(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        path=self.figures.currentData()
        if path:
            data=path.with_name(path.name+".data")
            if not data.is_dir(): self.show_error("此历史图片没有配套数据；旧版本输出需要重新分析或导出。"); return
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(data.resolve()))): self.show_error("无法打开数据目录。")

    def load_selected(self, *_):
        path = self.runs.currentData()
        if path:
            self.launch(lambda p,c: load_history(path,p,c,verify=False), self.loaded)

    def loaded(self, result):
        self.completed = result; self.image.clear(); self.figures.clear()
        for path in result["figures"]:
            self.figures.addItem(str(path.relative_to(result["directory"])), path)
        checks = result["checks"]
        integrity = "无产物哈希；完整性未核对" if not checks else f"产物哈希：{sum(s=='PASS' for _,s in checks)}/{len(checks)} 匹配"
        if not result.get("integrity_checked",True): integrity="完整性尚未核验；可点击 SHA-256 核验按钮。"
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
