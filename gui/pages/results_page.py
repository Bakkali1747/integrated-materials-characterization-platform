"""历史快照与保存图片浏览，不重新计算。"""
import json
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTextBrowser,
)

from gui.controllers.history_controller import history_index, load_history, read_figure
from gui.controllers.quality_controller import quality_text
from gui.pages.task_page import TaskPage
from gui.widgets.image_view import ImageView


class ResultsPage(TaskPage):
    def __init__(self):
        super().__init__("历史结果 · 只读已保存产物，不重新计算")
        self.entries = []
        self.folder = None
        open_button = QPushButton("打开历史结果目录")
        open_button.clicked.connect(self.choose_folder)
        self.search = QLineEdit()
        self.search.setPlaceholderText("筛选样品、日期（如 2026-10）、参数或路径")
        self.search.textChanged.connect(self.filter_runs)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["全部", "success", "failed", "cancelled", "partial_failure", "invalid"])
        self.status_filter.currentTextChanged.connect(self.filter_runs)
        self.runs = QComboBox()
        self.runs.activated.connect(self.load_selected)
        self.figures = QComboBox()
        self.figures.activated.connect(self.load_image)
        filters = QGridLayout()
        filters.setHorizontalSpacing(8)
        filters.setVerticalSpacing(8)
        filters.addWidget(open_button, 0, 0)
        filters.addWidget(self.search, 0, 1, 1, 3)
        filters.addWidget(self.status_filter, 0, 4)
        filters.addWidget(QLabel("运行"), 1, 0)
        filters.addWidget(self.runs, 1, 1, 1, 2)
        filters.addWidget(QLabel("图片"), 1, 3)
        filters.addWidget(self.figures, 1, 4)
        filters.setColumnStretch(1, 1)
        filters.setColumnStretch(2, 1)
        self.layout.addLayout(filters)
        split = QSplitter()
        tabs = QTabWidget()
        self.overview = QTextBrowser(); tabs.addTab(self.overview, "摘要 / QC")
        self.metadata = QTextBrowser(); tabs.addTab(self.metadata, "完整记录")
        self.integrity = QTextBrowser(); tabs.addTab(self.integrity, "产物核对")
        split.addWidget(tabs)
        self.image = ImageView()
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(self.image)
        split.addWidget(scroll)
        split.setSizes([420, 700]); self.layout.addWidget(split, 1)
        self.archive_button = QPushButton("归档旧运行…（默认先预演）")
        self.archive_button.setEnabled(False)
        self.archive_button.clicked.connect(self.archive_old)
        self.share_button = QPushButton("导出可分享记录…")
        self.share_button.clicked.connect(self.export_share)
        self.report_button = QPushButton("导出分析报告…（DOCX + PDF）")
        self.report_button.clicked.connect(self.save_report)
        self.verify_button = QPushButton("核验当前运行产物（SHA-256）")
        self.verify_button.clicked.connect(self.verify_selected)
        image_data_button = QPushButton("打开历史图片数据目录")
        image_data_button.clicked.connect(self.open_image_data)
        output_button = QPushButton("打开结果文件夹")
        output_button.clicked.connect(self.open_output)
        actions = QGridLayout()
        actions.setHorizontalSpacing(8)
        actions.setVerticalSpacing(8)
        actions.addWidget(self.archive_button, 0, 0)
        actions.addWidget(self.share_button, 0, 1)
        actions.addWidget(self.report_button, 0, 2)
        actions.addWidget(self.verify_button, 1, 0)
        actions.addWidget(image_data_button, 1, 1)
        actions.addWidget(output_button, 1, 2)
        self.layout.addLayout(actions)

    def set_simple(self, simple):
        """日常模式隐藏维护类操作，保留报告与核验。"""
        self.archive_button.setVisible(not simple)
        self.share_button.setVisible(not simple)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择 output / 样品 / 运行目录")
        if folder:
            self.scan(folder)

    def scan(self, folder):
        self.folder = str(folder)
        self.archive_button.setEnabled(True)
        self.launch(lambda p,c: history_index(folder,p,c), self.discovered)

    def _after_idle(self, callback):
        """等待当前后台线程真正结束后再启动下一项，避免重入被忽略。"""
        if self.busy:
            QTimer.singleShot(50, lambda: self._after_idle(callback))
        else:
            callback()

    def archive_old(self):
        """先扫描并预演，用户确认后才移动；清单写入 _archive/archive_manifest.json。"""
        if not self.folder:
            self.show_error("请先选择输出目录并扫描历史。")
            return
        days, accepted = QInputDialog.getInt(self, "归档旧运行", "归档早于多少天的运行？", 30, 0, 3650)
        if not accepted:
            return
        root = Path(self.folder)
        from core.maintenance import archive_runs, scan_runs, select_runs

        def preview(progress, cancelled):
            selected = select_runs(scan_runs(root), days)
            return archive_runs(selected, root, apply=False) if selected else None

        def ready(report):
            if not report:
                self.message.emit("没有符合条件、可归档的运行。")
                return
            answer = QMessageBox.question(
                self, "确认归档",
                f"将移动 {len(report['runs'])} 个运行（{report['total_bytes']/1024/1024:.1f} MB）到 "
                f"{root / '_archive'}。\n归档不删除文件，可随时移回。继续？")
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._after_idle(lambda: self._apply_archive(root, days))

        self.launch(preview, ready)

    def save_report(self):
        """从当前已加载运行生成中文 DOCX + PDF；不重新计算。"""
        if not self.completed:
            self.show_error("请先加载一个成功的运行记录。")
            return
        sample = self.completed["record"].get("sample", "sample")
        path, _ = QFileDialog.getSaveFileName(self, "保存分析报告", f"{sample}_report.docx",
                                              "Word 文档 (*.docx);;PDF (*.pdf)")
        if not path:
            return
        from export.report import export_report
        directory = self.completed["directory"]
        base = Path(path)
        kind = self.completed["record"].get("analysis_kind")
        if kind == "vsm_hysteresis":
            from export.vsm_report import export_vsm_report
            exporter = export_vsm_report
        elif kind == "xrd_peaks":
            from export.xrd_report import export_xrd_report
            exporter = export_xrd_report
        elif kind == "s_parameters":
            self.show_error("S 参数专用报告尚未实现；请使用 S 参数页面的图片导出或可分享记录。")
            return
        else:
            exporter = export_report
        self.launch(lambda p, c: exporter(directory, base, formats=("docx", "pdf")),
                    lambda files: self.message.emit("报告已生成：" + "；".join(str(item) for item in files)))

    def export_share(self):
        """导出当前选中运行的脱敏副本；不修改原运行。"""
        if not self.completed:
            self.show_error("请先加载一个运行记录，再导出可分享副本。")
            return
        parent = QFileDialog.getExistingDirectory(self, "选择分享副本的存放目录")
        if not parent:
            return
        source = Path(self.completed["directory"])
        target = Path(parent) / (source.name + "_share")
        from export.share_export import export_shareable
        self.launch(lambda p, c: export_shareable(source, target),
                    lambda output: self.message.emit(f"可分享副本：{output}"))

    def _apply_archive(self, root, days):
        from core.maintenance import archive_runs, scan_runs, select_runs

        def operation(progress, cancelled):
            return archive_runs(select_runs(scan_runs(root), days), root, apply=True)

        def done(report):
            self.message.emit(f"已归档 {len(report['runs'])} 个运行；清单见 "
                              f"{root / '_archive' / 'archive_manifest.json'}")
            if report.get("failures"):
                self.show_error(f"{len(report['failures'])} 个运行归档失败，详见清单。")
            self._after_idle(lambda: self.scan(str(root)))

        self.launch(operation, done)

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
        """核验下拉框当前选中的运行，而不是上一次已加载的运行。"""
        path = self.runs.currentData()
        if not path:
            self.show_error("请先选择一个运行记录，再核验全部产物。")
            return
        self.launch(lambda p,c: load_history(path,p,c,verify=True), self.loaded)

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
