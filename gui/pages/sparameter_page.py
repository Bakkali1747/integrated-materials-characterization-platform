"""独立的实测 S 参数页面；理论 RL 只在显式选择对照来源后叠图。"""
from pathlib import Path
import json
from PySide6.QtWidgets import (QLineEdit, QPushButton, QHBoxLayout, QComboBox, QLabel, QTextBrowser, QAbstractItemView,
                               QFileDialog, QSplitter, QTableWidget, QTableWidgetItem)
from gui.pages.task_page import TaskPage
from gui.widgets.plot_canvas import PlotCanvas
from gui.widgets.status_badge import StatusBadge
from gui.controllers.analysis_controller import ROOT
from gui.controllers.sparameter_controller import analyze_s_request, s_figure, theory_comparison
from plotting.theory_measured import plot_theory_measured, CAUTION
from plotting.style import plt


class SParameterPage(TaskPage):
    def __init__(self):
        super().__init__("GUI Phase 2 · Measured S Parameters")
        self.theory_runs = {}
        self.badge = StatusBadge("candidate_high_confidence", "S21/S12 字段顺序待厂商确认；与 Calculated RL from ε/μ 独立。")
        self.layout.addWidget(self.badge)
        self.file = QLineEdit()
        self.file.setPlaceholderText("选择 .sdat 实测文件")
        self.name = QLineEdit()
        self.name.setPlaceholderText("样品名称")
        self.schema = QLineEdit()
        self.schema.setPlaceholderText("可选 schema JSON；留空使用高置信候选映射")
        self.output = QLineEdit(str(ROOT / "output"))
        for label, entry, filter in [("SDAT 文件", self.file, "SDAT (*.sdat)"), ("Schema 配置", self.schema, "JSON (*.json)")]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(entry)
            button = QPushButton("选择…")
            button.clicked.connect(lambda checked=False, e=entry, f=filter: self.choose_file(e, f))
            row.addWidget(button)
            self.layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("样品")); row.addWidget(self.name)
        row.addWidget(QLabel("输出目录")); row.addWidget(self.output)
        out = QPushButton("选择目录")
        out.clicked.connect(self.choose_output)
        row.addWidget(out)
        self.start_button = QPushButton("开始 S 参数分析")
        self.start_button.clicked.connect(self.start_analysis)
        row.addWidget(self.start_button)
        self.layout.addLayout(row)
        row = QHBoxLayout()
        self.channel = QComboBox(); self.channel.addItems(["全部", "S11", "S21", "S12", "S22"])
        self.quantity = QComboBox()
        for label, key in [("Magnitude", "magnitude"), ("dB", "db"), ("Real / Imag", "real_imag"), ("Phase", "phase_deg"), ("R / T / A", "RTA")]:
            self.quantity.addItem(label, key)
        row.addWidget(self.channel); row.addWidget(self.quantity)
        update = QPushButton("更新显示"); update.clicked.connect(self.render_selected); row.addWidget(update)
        save = QPushButton("保存图片"); save.clicked.connect(self.save_selected); row.addWidget(save)
        open_button = QPushButton("打开结果目录"); open_button.clicked.connect(self.open_output); row.addWidget(open_button)
        self.layout.addLayout(row)
        self.plot = PlotCanvas(); self.plot.selector.hide()
        self.summary = QTextBrowser(); self.summary.setMinimumWidth(280)
        split = QSplitter(); split.addWidget(self.plot); split.addWidget(self.summary); split.setSizes([800, 330])
        self.layout.addWidget(split, 1)
        self.points = QTableWidget(); self.points.setMaximumHeight(160)
        self.points.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.layout.addWidget(self.points)
        row = QHBoxLayout()
        self.theory = QComboBox(); self.theory.addItem("先在单样品页面完成理论分析", None)
        row.addWidget(self.theory)
        compare = QPushButton("理论 / 实验对比"); compare.clicked.connect(self.compare_theory); row.addWidget(compare)
        self.layout.addLayout(row)
        self.caution = QLabel(CAUTION)
        self.caution.setWordWrap(True); self.caution.setStyleSheet("background:#fff1cc;padding:6px;")
        self.layout.addWidget(self.caution)
        self.display_builder = None

    def choose_file(self, entry, filter):
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", filter)
        if path:
            entry.setText(path)
            if entry is self.file:
                self.name.setText(Path(path).stem)

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "输出目录", self.output.text())
        if path:
            self.output.setText(path)

    def start_analysis(self):
        path, name, output, schema = self.file.text().strip(), self.name.text().strip(), self.output.text().strip(), self.schema.text().strip()
        if not path or not name or not output:
            self.show_error("请指定 .sdat 文件、样品名称和输出目录。")
            return
        self.launch(lambda progress, cancelled: analyze_s_request(path, name, output, schema, progress, cancelled), self.analyzed)

    def analyzed(self, result):
        self.completed = result
        record = result["record"]; qc = record["quality_checks"]
        self.badge.set_status(record["schema_status"], "非 manufacturer-confirmed；S21/S12 顺序与功率归一化待确认。")
        self.summary.setPlainText("\n".join([f"样品：{record['sample']}", f"来源：{record['raw_file']}",
            f"频率：{record['frequency_range_ghz']} GHz；{record['frequency_points']} 点", "缺失数据插值 OFF / clipping OFF",
            f"[COMPUTED] |Sij| 超限点数：{qc['magnitude_violation_counts']}",
            f"[COMPUTED] R+T 超容差点数：{qc['energy_violation_count']}",
            f"[COMPUTED] A<0 点数：{qc['negative_absorption_count']}（未 clip）",
            f"[COMPUTED] 互易性超容差点数：{qc['reciprocity']['violation_count']}",
            "容差：" + json.dumps(qc["tolerances"]), *qc["warnings"],
            "[COMMON] 一致性筛查不证明完整二端口无源性，也不确认厂商映射。", "S11_dB 不命名为 RL。"] ))
        if qc["negative_absorption_count"] or qc["energy_violation_count"] or sum(qc["magnitude_violation_counts"].values()):
            self.show_error("WARNING：存在负 A 或幅度/能量超限；请查看右侧 QC，原始数值没有裁剪。")
        columns = ["frequency_ghz"] + [f"{s}_db" for s in ("S11", "S21", "S12", "S22")] + ["R", "T", "A"]
        table = result["table"]
        self.points.setRowCount(len(table)); self.points.setColumnCount(len(columns)); self.points.setHorizontalHeaderLabels(columns)
        for i, values in enumerate(table[columns].itertuples(index=False, name=None)):
            for j, value in enumerate(values):
                self.points.setItem(i, j, QTableWidgetItem(f"{value:.8g}"))
        self.quantity.setCurrentIndex(0); self.channel.setCurrentIndex(0)
        self.plot.set_figures({"Magnitude": result["figures"]["magnitude"]})
        self.display_builder = lambda r=result: s_figure(r, "magnitude")

    def render_selected(self):
        if not self.completed:
            return
        result, quantity, channel = self.completed, self.quantity.currentData(), self.channel.currentText()
        builder = lambda: s_figure(result, quantity, channel)
        self.launch(lambda progress, cancelled: builder(), lambda fig: self.display(fig, builder))

    def display(self, figure, builder):
        self.plot.set_figures({"当前图": figure})
        self.display_builder = builder

    def save_selected(self):
        if self.display_builder:
            self.save_plot(self.display_builder)

    def add_theory(self, result):
        key = str(result["directory"])
        if key not in self.theory_runs:
            self.theory_runs[key] = {field: result[field] for field in ("directory", "record", "curve")}
            self.theory.addItem(f"{result['sample'].name} / {result['curve'].thickness_mm[0]:g} mm / {result['directory'].name}", key)

    def compare_theory(self):
        key = self.theory.currentData()
        if not self.completed or key not in self.theory_runs:
            self.show_error("请明确选择该样品的理论运行和实测 SDAT，程序不推断两种测量条件等价。")
            return
        theory, measured = self.theory_runs[key], self.completed
        def builder():
            fig = plot_theory_measured(theory["curve"], measured["table"])
            fig.suptitle("PENDING / candidate mapping", fontsize=10)
            plt.close(fig)
            return fig
        def completed(payload):
            fig, directory = payload
            self.display(fig, builder)
            self.message.emit(f"理论 / 实测对照已保存：{directory}")
        self.launch(lambda progress, cancelled: theory_comparison(theory, measured, progress, cancelled), completed)
