"""勾选样品、共同条件、十项比较与全部并列明细；批量目录流程留给 Phase 3。"""
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from gui.controllers.comparison_controller import compare_requests
from gui.pages.task_page import TaskPage
from gui.widgets.metrics_table import MetricsTable
from gui.widgets.parameter_panel import ParameterPanel
from gui.widgets.plot_canvas import PlotCanvas
from plotting.comparison_plot import plot_comparison
from plotting.style import PlotStyle, plt


class ComparisonPage(TaskPage):
    def __init__(self):
        super().__init__("GUI Phase 2 · 多样品比较（十项指标 / 原始采样点）")
        self.samples = QListWidget(); self.samples.setMaximumHeight(145)
        row = QHBoxLayout()
        for label, callback in [("添加文件", self.choose_files), ("全选", lambda: self.check_all(True)),
                                ("清空选择", lambda: self.check_all(False)), ("反选", self.invert)]:
            button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        self.layout.addLayout(row)
        split = QSplitter()
        controls = QWidget(); controls_layout = QVBoxLayout(controls)
        controls_layout.addWidget(QLabel("勾选样品（双击名称可修改）"))
        controls_layout.addWidget(self.samples)
        self.parameters = ParameterPanel()
        self.parameters.name.setText("比较使用列表名称")
        self.parameters.name.setEnabled(False)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(self.parameters); scroll.setMinimumWidth(300)
        self.plot = PlotCanvas()
        controls_layout.addWidget(scroll, 1)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.plot, "比较曲线")
        split.addWidget(controls); split.addWidget(self.tabs); split.setSizes([350, 800])
        self.layout.addWidget(split, 1)
        self.table = MetricsTable(); self.tabs.addTab(self.table, "指标汇总（可排序）")
        self.details = QTextBrowser(); self.tabs.addTab(self.details, "全部并列结果")
        self.note = QLabel("* 摘要位置为首个并列代表值；所有并列位置和频段见下方明细及 Excel。不同频率网格不作同条件排名。")
        self.note.setWordWrap(True); self.layout.addWidget(self.note)
        row = QHBoxLayout()
        self.start_button = QPushButton("分析勾选样品并比较"); self.start_button.clicked.connect(self.start_comparison)
        row.addWidget(self.start_button)
        for label, callback in [("保存当前图", self.save_selected), ("导出全部图片", self.save_all), ("打开结果 / Excel", self.open_output)]:
            button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        self.layout.addLayout(row)

    def add_source(self, path, name=None):
        """同路径不重复，名称可双击编辑；来源路径独立存储。"""
        path = Path(path).resolve()
        if path.suffix.lower() not in {".memp", ".csv", ".xlsx", ".xls"}:
            self.show_error("比较仅接受 ε/μ 数据，实测 S 参数请使用独立页面。")
            return
        if any(self.samples.item(i).data(Qt.ItemDataRole.UserRole) == str(path) for i in range(self.samples.count())):
            return
        item = QListWidgetItem(name or path.stem)
        item.setData(Qt.ItemDataRole.UserRole, str(path)); item.setToolTip(str(path))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable)
        item.setCheckState(Qt.CheckState.Checked)
        self.samples.addItem(item)

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择比较样品", "", "ε/μ 数据 (*.memp *.csv *.xlsx *.xls)")
        for path in paths:
            self.add_source(path)

    def check_all(self, checked):
        for i in range(self.samples.count()):
            self.samples.item(i).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def invert(self):
        for i in range(self.samples.count()):
            item = self.samples.item(i)
            item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)

    def selected_requests(self):
        requests = []
        for i in range(self.samples.count()):
            item = self.samples.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                requests.append(replace(self.parameters.request(item.data(Qt.ItemDataRole.UserRole)), name=item.text().strip()))
        return requests

    def start_comparison(self):
        try:
            requests = self.selected_requests()
            if len(requests) < 2:
                raise ValueError("请选择至少两个 ε/μ 样品。")
            if any(not r.name for r in requests) or len({r.name for r in requests}) != len(requests):
                raise ValueError("样品名必须非空且唯一，可双击列表名称修改。")
            output = requests[0].output
        except Exception as error:
            self.show_error(str(error)); return
        self.launch(lambda progress, cancelled: compare_requests(requests, output, progress, cancelled, dpi=requests[0].dpi), self.analyzed)

    def analyzed(self, result):
        self.completed = result
        self.plot.set_figures(result["figures"])
        comparison = result["record"]["comparison"]
        comparable = comparison.get("identical_frequency_grids", False)
        self.table.load_rows(result["summaries"], comparable)
        notes = comparison.get("notes", [])
        self.note.setText("\n".join(notes + ["* 摘要位置取首个并列代表；以下明细及 Excel 保留全部并列值。",
            f"成功 {result['record']['success_count']} / 失败 {result['record']['failure_count']}"]))
        self.note.setStyleSheet("background:#fff1cc;padding:5px;" if not comparable else "")
        self.details.setPlainText(json.dumps({"全部 RLmin 点": result["minima"], "全部最大 EAB 频段": result["bands"]}, ensure_ascii=False, indent=2))

    def save_selected(self):
        if not self.completed or not self.plot.current_figure():
            return
        self.save_plot(self.figure_builder(self.plot.selector.currentData()))

    def save_all(self):
        if self.completed:
            self.save_all_plots({key:self.figure_builder(key) for key in self.completed["figures"]})

    def figure_builder(self, metric):
        result, dpi = self.completed, self.export_dpi
        # 读取已输出的比较长表仅用于重绘；不重新对齐不同采样网格。
        def builder():
            relative = Path("figures") / f"{metric}.csv"
            path = result["directory"] / relative
            if hashlib.sha256(path.read_bytes()).hexdigest() != result["record"]["artifacts_sha256"][str(relative)]:
                raise ValueError("比较数据在分析后已改变，拒绝导出与记录不一致的图片。")
            frame = pd.read_csv(path)
            axis = "thickness_mm" if metric == "eab_minus10_db_ghz" else "frequency_ghz"
            series = [{"name": name, "x": group[axis].to_numpy(), "y": group[metric].to_numpy()} for name, group in frame.groupby("sample", sort=False)]
            fig = plot_comparison(series, metric, PlotStyle(dpi=dpi), result["curve_thickness"])
            plt.close(fig)
            return fig
        return builder
