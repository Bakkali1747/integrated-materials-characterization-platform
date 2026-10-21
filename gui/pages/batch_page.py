"""批量来源表与后台任务界面。"""
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea, QSplitter, QTextBrowser, QTreeWidget, QTreeWidgetItem

from gui.controllers.batch_controller import run_batch_requests, scan_folder
from gui.pages.task_page import TaskPage
from gui.widgets.parameter_panel import ParameterPanel
from gui.widgets.status_badge import StatusBadge


class BatchPage(TaskPage):
    member_changed = Signal(object)

    def __init__(self):
        super().__init__("批量分析 · 同目录同名归组，逐来源独立输出")
        self.items = []; self.rows = []; self.states = []
        self.layout.addWidget(StatusBadge("PENDING", "MEMP 虚部 / 商业对照 PENDING；SDAT candidate_high_confidence，S21/S12 顺序待厂商确认。"))
        choose = QPushButton("选择文件夹（仅扫描当前层）"); choose.clicked.connect(self.choose_folder)
        self.layout.addWidget(choose)
        split = QSplitter()
        self.parameters = ParameterPanel(); self.parameters.name.setText("batch")
        self.parameters.name.setEnabled(False)
        scroll = QScrollArea(); scroll.setObjectName("panelCard"); scroll.setWidgetResizable(True); scroll.setWidget(self.parameters)
        split.addWidget(scroll)
        self.table = QTreeWidget(); self.table.setHeaderLabels(["样品 / 来源", "MEMP", "SDAT", "状态", "点数 / 频率 GHz"])
        for column, width in enumerate((260, 65, 65, 140, 180)):
            self.table.setColumnWidth(column, width)
        self.table.itemSelectionChanged.connect(self.selected)
        split.addWidget(self.table); split.setSizes([320, 780]); self.layout.addWidget(split, 1)
        self.details = QTextBrowser(); self.details.setMaximumHeight(150)
        self.details.setPlainText("选择文件夹后，这里显示当前来源的解析状态与建议。")
        self.layout.addWidget(self.details)
        self.counts = QLabel("总来源 0 / 完成 0 / 失败 0"); self.layout.addWidget(self.counts)
        self.start_button = QPushButton("开始批量分析"); self.start_button.setObjectName("primaryButton"); self.start_button.clicked.connect(self.start)
        self.layout.addWidget(self.start_button)
        open_button = QPushButton("打开输出目录"); open_button.clicked.connect(self.open_output); self.layout.addWidget(open_button)
        self.member_changed.connect(self.member_update)

    def choose_folder(self):
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "选择原始数据目录")
        if folder:
            self.scan(folder)

    def scan(self, folder):
        try:
            options = self.parameters.parser_options()
            self.launch(lambda p,c: scan_folder(folder, options, p,c), self.scanned)
        except Exception as error:
            self.show_error(str(error))

    def scanned(self, items):
        self.items = items; self.rows = []; self.states = []; self.table.clear()
        groups = {}
        for info in items:
            key = (info["path"].parent, info["sample"])
            if key not in groups:
                groups[key] = QTreeWidgetItem(self.table, [info["sample"]])
            parent = groups[key]
            if info["format"] in {".memp", ".sdat"}:
                parent.setText(1 if info["format"] == ".memp" else 2, "✓")
            row = QTreeWidgetItem(parent, [info["path"].name, "", "", info["status"], f"{info['points']} / {info['frequency']}"])
            self.rows.append(row); self.states.append(dict(info))
        self.table.expandAll()
        if self.rows:
            self.table.setCurrentItem(self.rows[0])
        self.counts.setText(f"样品 {len(groups)} / 来源 {len(items)} / 解析失败 {sum(i['status']=='FAIL' for i in items)}")

    def start(self):
        if self.busy:
            return
        try:
            requests = [replace(self.parameters.request(i["path"]), name=i["sample"]) for i in self.items]
            output = Path(self.parameters.output.text()).expanduser().resolve()
            self.states = [dict(sample=i["sample"], status="not_started") for i in self.items]
            for row in self.rows:
                row.setText(3, "not_started")
            self.launch(lambda p,c: run_batch_requests(requests, output, p,c, self.member_changed.emit,
                                                       reuse=self.parameters.reuse.isChecked()), self.analyzed)
        except Exception as error:
            self.show_error(str(error))

    def member_update(self, member):
        index = member["index"]; self.states[index] = member
        self.rows[index].setText(3, member["status"])
        self.counts.setText(f"总来源 {len(self.rows)} / 完成 {sum(m['status']=='success' for m in self.states)} / 失败 {sum(m['status']=='failed' for m in self.states)} / 当前 {member['sample']}")
        self.selected()

    def selected(self):
        row = self.table.currentItem()
        if row in self.rows:
            member = self.states[self.rows.index(row)]
            lines = [f"样品：{member['sample']}", f"状态：{member['status']}",
                     f"来源：{member.get('raw_file',member.get('path','未记录'))}"]
            if member.get("error"):
                lines += ["问题："+member["error"], "建议：检查原始数据、列映射和单位后重新扫描；其他来源结果保留。"]
            if member.get("run_directory"):
                lines.append("结果目录："+member["run_directory"])
            lines += [f"{name}: {state} — {note}" for name,state,note in member.get("quality_control",[])]
            self.details.setPlainText("\n".join(lines))

    def analyzed(self, result):
        self.completed = result
        r = result["record"]
        self.counts.setText(f"{r['status']} · 成功 {r['success_count']} / 失败 {r['failed_count']} / 警告 {r.get('warning_count',0)} / 取消 {r['cancelled_count']} / 未开始 {r['not_started_count']}")
