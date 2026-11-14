"""已完成运行的多类型比较基类；只读取已保存结果，不重新分析原始文件。"""

import json
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
)

from core import __version__
from export.origin_export import save_figure_bundle
from export.provenance import artifact_hashes, figure_provenance, git_state
from gui.controllers.analysis_controller import ROOT
from gui.pages.task_page import TaskPage
from gui.widgets.plot_canvas import PlotCanvas


class RunComparisonPage(TaskPage):
    """通用“添加已完成运行 → 叠加图 + 指标表 + 追溯记录”页面。"""

    def __init__(self, title, kind, loader, figure_builder, headers, row_builder,
                 placeholder="添加至少两个已完成运行后生成比较"):
        super().__init__(title)
        self.kind = kind
        self.loader = loader
        self.figure_builder = figure_builder
        self.headers = headers
        self.row_builder = row_builder
        self.runs = []
        self.sources = QListWidget()
        self.sources.setMaximumHeight(115)
        self.sources.setToolTip("仅接受已完成运行目录；不会重新分析原始文件")
        row = QHBoxLayout()
        for label, callback in (("添加运行目录", self.choose_run), ("移除", self.remove_selected),
                                ("清空", self.clear_runs)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        self.layout.addLayout(row)
        self.layout.addWidget(QLabel("已完成运行（比较只读取已保存结果）"))
        self.layout.addWidget(self.sources)
        from PySide6.QtWidgets import QLineEdit
        self.output = QLineEdit(str(ROOT / "output"))
        output_button = QPushButton("输出目录")
        output_button.clicked.connect(self.choose_output)
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("输出"))
        output_row.addWidget(self.output)
        output_row.addWidget(output_button)
        self.layout.addLayout(output_row)
        split = QSplitter()
        self.plot = PlotCanvas()
        self.plot.set_placeholder(placeholder)
        split.addWidget(self.plot)
        right = QTextBrowser()
        right.setMinimumWidth(320)
        right.setPlainText("选择已完成运行后生成比较；摘要、状态和来源显示在这里。")
        self.summary = right
        split.addWidget(self.summary)
        split.setSizes([850, 320])
        self.layout.addWidget(split, 1)
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setMaximumHeight(190)
        self.layout.addWidget(self.table)
        row = QHBoxLayout()
        self.start_button = QPushButton("生成比较")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start_comparison)
        row.addWidget(self.start_button)
        open_button = QPushButton("打开输出目录")
        open_button.clicked.connect(self.open_output)
        row.addWidget(open_button)
        save_button = QPushButton("保存当前图")
        save_button.clicked.connect(lambda: self.save_plot(lambda: self.plot.current_figure()))
        row.addWidget(save_button)
        self.layout.addLayout(row)

    def choose_run(self):
        directory = QFileDialog.getExistingDirectory(self, f"选择已完成 {self.kind} 运行目录")
        if directory:
            self.add_run(directory)

    def add_run(self, directory):
        try:
            run = self.loader(Path(directory))
            record = run["record"]
            if record.get("analysis_kind") != self.kind:
                raise ValueError(f"该目录不是 {self.kind} 运行（记录类型 {record.get('analysis_kind')}）。")
            resolved = Path(run["directory"]).resolve()
            if any(Path(item["directory"]).resolve() == resolved for item in self.runs):
                return
            run["directory"] = resolved
            self.runs.append(run)
            sample = record.get("sample") or resolved.name
            self.sources.addItem(f"{sample} · {resolved}")
            self.message.emit(f"已添加 {sample}；比较不会重新计算。")
        except Exception as error:
            self.show_error(str(error))

    def remove_selected(self):
        row = self.sources.currentRow()
        if row >= 0:
            self.sources.takeItem(row)
            self.runs.pop(row)

    def clear_runs(self):
        self.sources.clear()
        self.runs = []

    def choose_output(self):
        directory = QFileDialog.getExistingDirectory(self, "选择比较输出目录")
        if directory:
            self.output.setText(directory)

    def start_comparison(self):
        if len(self.runs) < 2:
            self.show_error("至少添加两个已完成运行。")
            return
        output = Path(self.output.text()).expanduser().resolve()
        directory = output / f"{self.kind}_comparison" / (
            datetime.now().strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8])
        runs = list(self.runs)
        headers = list(self.headers)
        row_builder = self.row_builder
        figure_builder = self.figure_builder
        dpi = self.export_dpi

        def operation(progress, cancelled):
            directory.mkdir(parents=True)
            if cancelled():
                raise RuntimeError("比较已取消。")
            progress(20, "生成叠加图")
            figures = figure_builder(runs)
            folder = directory / "figures"
            folder.mkdir(exist_ok=True)
            record = {
                "analysis_kind": f"{self.kind}_comparison", "comparison_type": self.kind,
                "software_version": __version__, "git": git_state(),
                "analysis_date": datetime.now().astimezone().isoformat(), "status": "success",
                "sample": f"{self.kind} comparison", "interpolation": "OFF",
                "sources": [{"directory": str(run["directory"]),
                             "sample": run["record"].get("sample"),
                             "run_id": run["record"].get("run_id"),
                             "raw_sha256": run["record"].get("raw_sha256")} for run in runs],
            }
            provenance = figure_provenance(record, dpi=dpi)
            for key, figure in figures.items():
                if cancelled():
                    raise RuntimeError("比较已取消。")
                save_figure_bundle(figure, folder / f"{key}.png", dpi=dpi, provenance=provenance)
            rows = [row_builder(run) for run in runs]
            pd.DataFrame(rows, columns=headers).to_csv(directory / "comparison_metrics.csv", index=False)
            record["artifacts_sha256"] = artifact_hashes(directory)
            (directory / "comparison_record.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            progress(100, "比较完成")
            return {"directory": directory, "record": record, "figures": figures,
                    "rows": rows, "headers": headers}

        self.launch(operation, self.analyzed)

    def analyzed(self, result):
        self.completed = result
        self.plot.set_figures(result["figures"])
        self.table.setRowCount(len(result["rows"]))
        for row_index, row in enumerate(result["rows"]):
            for column_index, value in enumerate(row):
                self.table.setItem(row_index, column_index, QTableWidgetItem("" if value is None else str(value)))
        sources = "\n".join(f"{run['record'].get('sample')}：{run['record'].get('status')} / "
                            f"{run['record'].get('validation_status', 'pending')}" for run in self.runs)
        self.summary.setPlainText(
            f"比较类型：{self.kind}\n运行数：{len(self.runs)}\n输出：{result['directory']}\n\n"
            f"来源：\n{sources}\n\n[COMMON] 只读取已完成运行；未重新分析、未插值、未改变验证状态。")
        self.message.emit(f"比较完成：{result['directory']}")
