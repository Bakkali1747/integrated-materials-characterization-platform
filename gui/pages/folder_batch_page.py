"""按数据类型扫描目录并逐文件批量分析；失败隔离，逐来源输出。"""

import json
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
)

from core import __version__
from export.provenance import artifact_hashes, git_state
from gui.controllers.analysis_controller import ROOT
from gui.pages.task_page import TaskPage


class FolderBatchPage(TaskPage):
    def __init__(self, title, kind, suffixes, analyzer, headers, row_builder):
        super().__init__(title)
        self.kind = kind
        self.suffixes = {suffix.lower() for suffix in suffixes}
        self.analyzer = analyzer
        self.headers = headers
        self.row_builder = row_builder
        self.files = []
        row = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("选择包含原始数据的目录（仅扫描当前层）")
        choose = QPushButton("选择目录")
        choose.clicked.connect(self.choose_folder)
        row.addWidget(QLabel("目录"))
        row.addWidget(self.folder)
        row.addWidget(choose)
        self.layout.addLayout(row)
        self.output = QLineEdit(str(ROOT / "output"))
        output_button = QPushButton("输出目录")
        output_button.clicked.connect(self.choose_output)
        row = QHBoxLayout()
        row.addWidget(QLabel("输出"))
        row.addWidget(self.output)
        row.addWidget(output_button)
        self.layout.addLayout(row)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["文件", "状态", "说明"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.layout.addWidget(self.table, 1)
        self.log = QTextBrowser()
        self.log.setMaximumHeight(150)
        self.log.setPlainText("选择目录后逐文件分析；单个失败不会中断其余来源。")
        self.layout.addWidget(self.log)
        row = QHBoxLayout()
        self.start_button = QPushButton("开始批量分析")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start)
        row.addWidget(self.start_button)
        open_button = QPushButton("打开输出目录")
        open_button.clicked.connect(self.open_output)
        row.addWidget(open_button)
        self.layout.addLayout(row)

    def choose_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "选择原始数据目录")
        if directory:
            self.folder.setText(directory)
            self.scan()

    def choose_output(self):
        directory = QFileDialog.getExistingDirectory(self, "选择批量输出目录")
        if directory:
            self.output.setText(directory)

    def scan(self):
        root = Path(self.folder.text()).expanduser()
        if not root.is_dir():
            self.show_error("请选择存在的目录。")
            return
        self.files = sorted(path for path in root.iterdir()
                            if path.is_file() and not path.is_symlink()
                            and path.suffix.lower() in self.suffixes)
        self.table.setRowCount(len(self.files))
        for index, path in enumerate(self.files):
            self.table.setItem(index, 0, QTableWidgetItem(path.name))
            self.table.setItem(index, 1, QTableWidgetItem("待分析"))
            self.table.setItem(index, 2, QTableWidgetItem(""))
        self.log.setPlainText(f"找到 {len(self.files)} 个 {self.kind} 文件。")
        if not self.files:
            self.show_error("目录中没有匹配的原始文件。")

    def start(self):
        if self.busy:
            return
        if not self.files:
            self.scan()
        if not self.files:
            return
        root = Path(self.output.text()).expanduser().resolve()
        directory = root / "batches" / (
            datetime.now().strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8])
        files = list(self.files)
        dpi = self.export_dpi
        headers = list(self.headers)
        analyzer = self.analyzer
        row_builder = self.row_builder
        kind = self.kind

        def operation(progress, cancelled):
            directory.mkdir(parents=True)
            sources_dir = directory / "sources"
            members, rows = [], []
            for index, path in enumerate(files):
                if cancelled():
                    members.append({"file": str(path), "status": "cancelled"})
                    break
                progress(int(index * 100 / len(files)), f"{path.name}：分析")
                try:
                    result = analyzer(path, path.stem, sources_dir, progress, cancelled, dpi)
                    record = result["record"]
                    member = {"file": str(path), "sample": record.get("sample"),
                              "status": record.get("status"), "run_directory": str(result["directory"]),
                              "validation_status": record.get("validation_status")}
                    rows.append(row_builder(result))
                except Exception as error:
                    member = {"file": str(path), "status": "failed",
                              "error": f"{type(error).__name__}: {error}"}
                members.append(member)
            progress(95, "写入批量记录")
            record = {
                "analysis_kind": f"{kind}_batch", "batch_type": kind,
                "software_version": __version__, "git": git_state(),
                "analysis_date": datetime.now().astimezone().isoformat(),
                "status": "success" if all(m["status"] == "success" for m in members) else "partial_failure",
                "interpolation": "OFF", "members": members,
            }
            pd.DataFrame(members).to_csv(directory / "sources.csv", index=False)
            if rows:
                pd.DataFrame(rows, columns=headers).to_csv(directory / "batch_summary.csv", index=False)
            record["artifacts_sha256"] = artifact_hashes(directory)
            (directory / "batch_record.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            progress(100, "批量分析完成")
            return {"directory": directory, "record": record, "rows": rows, "headers": headers}

        self.launch(operation, self.analyzed)

    def _set_row(self, index, status, detail):
        if 0 <= index < self.table.rowCount():
            self.table.setItem(index, 1, QTableWidgetItem(status))
            self.table.setItem(index, 2, QTableWidgetItem(detail))

    def analyzed(self, result):
        self.completed = result
        for index, member in enumerate(result["record"]["members"]):
            detail = member.get("error") or member.get("run_directory", "")
            self._set_row(index, member["status"], detail)
        self.log.setPlainText(
            f"批量输出：{result['directory']}\n"
            f"来源：{len(result['record']['members'])}；成功："
            f"{sum(item['status'] == 'success' for item in result['record']['members'])}；"
            f"失败：{sum(item['status'] == 'failed' for item in result['record']['members'])}")
        self.message.emit(f"批量分析完成：{result['directory']}")
