"""项目与样品工作区；只保存引用和追溯信息，不修改原始文件。"""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from application_paths import user_data_root
from core.common import (
    MeasurementType,
    ValidationStatus,
    WorkspaceRepository,
    analysis_type_label,
    link_electromagnetic_run,
    link_sparameter_run,
    link_vsm_run,
)

# 阶段 B 只把 ε/μ 数据与实测 S 参数接入工作区；VSM 使用独立文件与页面。
ELECTROMAGNETIC_SOURCES = {".csv", ".xlsx", ".xls", ".memp"}
SPARAMETER_SOURCE = ".sdat"
VSM_SOURCES = {".csv", ".xlsx", ".xls", ".txt"}


def _tags(text: str) -> list[str]:
    return [item.strip() for item in text.replace("，", ",").split(",") if item.strip()]


class _ProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建项目")
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("例如：片状 CIP 磁性能调控")
        self.description = QTextEdit()
        self.description.setMaximumHeight(90)
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("使用逗号分隔")
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(70)
        form.addRow("项目名称 *", self.name)
        form.addRow("描述", self.description)
        form.addRow("标签", self.tags)
        form.addRow("备注", self.notes)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _accept(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "信息不完整", "请输入项目名称。")
            return
        self.accept()


class _SampleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建样品")
        form = QFormLayout(self)
        self.sample_id = QLineEdit()
        self.sample_id.setPlaceholderText("例如：FCIP-03；留空则自动生成")
        self.name = QLineEdit()
        self.material = QLineEdit()
        self.batch = QLineEdit()
        self.preparation_date = QLineEdit()
        self.preparation_date.setPlaceholderText("YYYY-MM-DD")
        self.filler_ratio = QLineEdit()
        self.composition = QTextEdit(); self.composition.setMaximumHeight(60)
        self.processing = QTextEdit(); self.processing.setMaximumHeight(60)
        self.tags = QLineEdit()
        self.notes = QTextEdit(); self.notes.setMaximumHeight(60)
        form.addRow("样品 ID", self.sample_id)
        form.addRow("样品名称 *", self.name)
        form.addRow("材料体系", self.material)
        form.addRow("批次", self.batch)
        form.addRow("制备日期", self.preparation_date)
        form.addRow("填料比例", self.filler_ratio)
        form.addRow("组成", self.composition)
        form.addRow("处理条件", self.processing)
        form.addRow("标签", self.tags)
        form.addRow("备注", self.notes)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _accept(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "信息不完整", "请输入样品名称。")
            return
        self.accept()


class _MeasurementDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加测试")
        self.files: list[Path] = []
        form = QFormLayout(self)
        self.kind = QComboBox()
        for item in MeasurementType:
            self.kind.addItem(item.label, item.value)
        choose = QPushButton("选择一个或多个原始文件…")
        choose.clicked.connect(self.choose_files)
        self.file_label = QLabel("尚未选择文件")
        self.file_label.setWordWrap(True)
        self.instrument = QLineEdit()
        self.date = QLineEdit(); self.date.setPlaceholderText("YYYY-MM-DD")
        form.addRow("测试类型 *", self.kind)
        form.addRow("原始文件 *", choose)
        form.addRow("", self.file_label)
        form.addRow("仪器", self.instrument)
        form.addRow("测试日期", self.date)
        hint = QLabel("文件保持原位且只读；工作区仅保存绝对路径和 SHA-256。")
        hint.setObjectName("formHint")
        hint.setWordWrap(True)
        form.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择原始测试文件")
        if files:
            self.files = [Path(item) for item in files]
            self.file_label.setText("\n".join(str(item) for item in self.files))

    def _accept(self):
        if not self.files:
            QMessageBox.warning(self, "信息不完整", "请至少选择一个原始测试文件。")
            return
        self.accept()


class WorkspacePage(QWidget):
    message = Signal(str)
    analysis_requested = Signal(object)
    sparameter_analysis_requested = Signal(object)
    vsm_analysis_requested = Signal(object)
    run_load_requested = Signal(object)

    def __init__(self, repository: WorkspaceRepository | None = None, parent=None):
        super().__init__(parent)
        self.schema_error = ""
        if repository is not None:
            self.repository = repository
        else:
            try:
                self.repository = WorkspaceRepository(user_data_root() / "workspace")
            except Exception as error:  # 工作区损坏时应显示原因，而不是让整个客户端无法启动
                self.repository = None
                self.schema_error = str(error)
        self.current_project_id: str | None = None
        self.current_sample_id: str | None = None
        self.current_measurement_id: str | None = None
        self.current_run_id: str | None = None
        self.current_runs: dict = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 14, 8, 8)
        layout.setSpacing(10)
        title = QLabel("项目与样品工作区")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("以项目—样品—测试—分析运行为主线；原始文件保持原位，工作区保存路径、SHA-256 与科研状态。")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        self.schema_label = QLabel("")
        self.schema_label.setObjectName("formHint")
        self.schema_label.setWordWrap(True)
        layout.addWidget(self.schema_label)
        self._refresh_schema_label()

        actions = QHBoxLayout()
        self.new_project_button = QPushButton("新建项目")
        self.new_project_button.setObjectName("primaryButton")
        self.new_project_button.clicked.connect(self.show_new_project)
        new_project = self.new_project_button
        self.new_sample_button = QPushButton("新建样品")
        self.new_sample_button.clicked.connect(self.show_new_sample)
        self.measurement_button = QPushButton("添加测试")
        self.measurement_button.clicked.connect(self.show_new_measurement)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh)
        actions.addWidget(new_project)
        actions.addWidget(self.new_sample_button)
        actions.addWidget(self.measurement_button)
        actions.addStretch()
        actions.addWidget(refresh)
        layout.addLayout(actions)

        split = QSplitter()
        self.projects = QTableWidget(0, 3)
        self.projects.setHorizontalHeaderLabels(["项目", "样品数", "更新时间"])
        self._configure_table(self.projects)
        self.projects.itemSelectionChanged.connect(self._project_selected)
        self.projects.horizontalHeader().setStretchLastSection(True)
        split.addWidget(self.projects)

        tabs = QTabWidget()
        project_tab = QWidget()
        project_layout = QVBoxLayout(project_tab)
        self.project_summary = QTextBrowser()
        self.project_summary.setMaximumHeight(118)
        project_layout.addWidget(self.project_summary)
        self.samples = QTableWidget(0, 6)
        self.samples.setHorizontalHeaderLabels(["样品 ID", "样品名称", "Electromagnetic", "VSM", "XRD", "更新时间"])
        self._configure_table(self.samples)
        self.samples.itemSelectionChanged.connect(self._sample_selected)
        self.samples.horizontalHeader().setStretchLastSection(True)
        project_layout.addWidget(self.samples, 1)
        tabs.addTab(project_tab, "项目样品")

        sample_tab = QWidget()
        sample_layout = QVBoxLayout(sample_tab)
        self.sample_summary = QTextBrowser()
        sample_layout.addWidget(self.sample_summary)
        self.measurements = QTableWidget(0, 5)
        self.measurements.setHorizontalHeaderLabels(["测试类型", "原始文件", "状态", "仪器", "测试日期"])
        self._configure_table(self.measurements)
        self.measurements.itemSelectionChanged.connect(self._measurement_selected)
        self.measurements.horizontalHeader().setStretchLastSection(True)
        sample_layout.addWidget(self.measurements, 1)

        measurement_actions = QHBoxLayout()
        self.verify_button = QPushButton("核验来源文件")
        self.verify_button.clicked.connect(self.verify_selected_measurement)
        self.analyze_button = QPushButton("用此测试开始电磁分析")
        self.analyze_button.setObjectName("primaryButton")
        self.analyze_button.clicked.connect(self.start_measurement_analysis)
        self.sparameter_button = QPushButton("用此测试开始S参数分析")
        self.sparameter_button.clicked.connect(self.start_measurement_sparameter_analysis)
        self.vsm_button = QPushButton("用此测试开始VSM分析")
        self.vsm_button.clicked.connect(self.start_measurement_vsm_analysis)
        measurement_actions.addWidget(self.verify_button)
        measurement_actions.addWidget(self.analyze_button)
        measurement_actions.addWidget(self.sparameter_button)
        measurement_actions.addWidget(self.vsm_button)
        measurement_actions.addStretch()
        sample_layout.addLayout(measurement_actions)
        self.verify_result = QLabel("")
        self.verify_result.setObjectName("formHint")
        self.verify_result.setWordWrap(True)
        sample_layout.addWidget(self.verify_result)

        runs_title = QLabel("分析运行（追加记录；同一测试重新分析不会覆盖历史）")
        runs_title.setObjectName("sectionTitle")
        sample_layout.addWidget(runs_title)
        self.runs = QTableWidget(0, 5)
        self.runs.setHorizontalHeaderLabels(["完成时间", "类型", "状态", "警告", "结果目录"])
        self._configure_table(self.runs)
        self.runs.itemSelectionChanged.connect(self._run_selected)
        self.runs.cellDoubleClicked.connect(lambda row, column: self.open_selected_run())
        self.runs.horizontalHeader().setStretchLastSection(True)
        sample_layout.addWidget(self.runs, 1)
        run_actions = QHBoxLayout()
        self.open_run_button = QPushButton("打开运行结果目录")
        self.open_run_button.clicked.connect(self.open_selected_run)
        self.load_run_button = QPushButton("载入运行结果")
        self.load_run_button.setToolTip("读取该运行已保存的数值结果与摘要，不重新计算。")
        self.load_run_button.clicked.connect(self.load_selected_run)
        run_actions.addWidget(self.open_run_button)
        run_actions.addWidget(self.load_run_button)
        run_actions.addStretch()
        sample_layout.addLayout(run_actions)
        tabs.addTab(sample_tab, "样品详情")
        self.tabs = tabs
        split.addWidget(tabs)
        split.setSizes([330, 900])
        layout.addWidget(split, 1)
        self.refresh()

    @staticmethod
    def _configure_table(table: QTableWidget):
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)

    @staticmethod
    def _selected_id(table: QTableWidget) -> str | None:
        row = table.currentRow()
        item = table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _refresh_schema_label(self):
        if self.repository is None:
            self.schema_label.setStyleSheet("color: #a03127;")
            self.schema_label.setText(f"工作区不可用：{self.schema_error or '未知错误'}（现有数据未被修改）")
            return
        info = self.repository.schema_info()
        text = f"工作区 schema v{info['schema_version']} · {self.repository.root}"
        if info["migrated"]:
            text += f" · 已从 v{info['previous_version']} 迁移"
        elif info["created"]:
            text += " · 新建"
        self.schema_label.setText(text)

    def _require_repository(self):
        if self.repository is None:
            raise ValueError(self.schema_error or "工作区不可用。")
        return self.repository

    def refresh(self, *, select_project: str | None = None, select_sample: str | None = None):
        if self.repository is None:
            self.current_project_id = None
            self.current_sample_id = None
            self.current_measurement_id = None
            self.current_run_id = None
            self.projects.setRowCount(0)
            self.samples.setRowCount(0)
            self.measurements.setRowCount(0)
            self.runs.setRowCount(0)
            self.project_summary.setPlainText(f"无法打开工作区：\n{self.schema_error}")
            self.sample_summary.setPlainText("工作区不可用时不会读取或改写任何项目数据。")
            for button in (self.new_project_button, self.new_sample_button, self.measurement_button):
                button.setEnabled(False)
            self._refresh_measurement_actions()
            self._refresh_run_actions()
            return
        projects = self.repository.list_projects()
        desired_project = select_project or self.current_project_id
        self.projects.setRowCount(len(projects))
        selected_row = 0 if projects else -1
        for row, project in enumerate(projects):
            name = QTableWidgetItem(project.project_name)
            name.setData(Qt.ItemDataRole.UserRole, project.project_id)
            self.projects.setItem(row, 0, name)
            self.projects.setItem(row, 1, QTableWidgetItem(str(len(project.sample_ids))))
            self.projects.setItem(row, 2, QTableWidgetItem(project.updated_at))
            if project.project_id == desired_project:
                selected_row = row
        if selected_row >= 0:
            self.projects.selectRow(selected_row)
            self._load_project(projects[selected_row].project_id, select_sample or self.current_sample_id)
        else:
            self.current_project_id = None
            self.current_sample_id = None
            self.project_summary.setPlainText("尚未创建项目。点击“新建项目”开始。")
            self.sample_summary.setPlainText("请选择样品。")
            self.samples.setRowCount(0)
            self.measurements.setRowCount(0)
            self.runs.setRowCount(0)
            self.current_measurement_id = None
            self.current_run_id = None
            self.verify_result.setText("")
            self.new_sample_button.setEnabled(False)
            self.measurement_button.setEnabled(False)
            self._refresh_measurement_actions()
            self._refresh_run_actions()

    def _project_selected(self):
        identifier = self._selected_id(self.projects)
        if identifier:
            self._load_project(identifier)

    def _load_project(self, project_id: str, select_sample: str | None = None):
        project = self.repository.get_project(project_id)
        self.current_project_id = project.project_id
        self.current_sample_id = None
        self.project_summary.setPlainText(
            f"{project.project_name}\n项目 ID：{project.project_id}\n{project.description or '暂无描述'}\n"
            f"标签：{', '.join(project.tags) if project.tags else '无'}")
        samples = self.repository.list_samples(project.project_id)
        self.samples.setRowCount(len(samples))
        selected_row = -1
        for row, sample in enumerate(samples):
            item = QTableWidgetItem(sample.sample_id)
            item.setData(Qt.ItemDataRole.UserRole, sample.sample_id)
            self.samples.setItem(row, 0, item)
            self.samples.setItem(row, 1, QTableWidgetItem(sample.sample_name))
            measurements = self.repository.list_measurements(project.project_id, sample.sample_id)
            latest = {}
            for measurement in measurements:
                latest.setdefault(measurement.measurement_type, measurement.validation_status)
            for column, kind in enumerate(("electromagnetic", "vsm", "xrd"), start=2):
                status = latest.get(kind)
                display = "○ Missing" if status is None else {
                    "VALIDATED": "✓ Available", "WARNING": "⚠ Warning", "PENDING": "! PENDING"
                }.get(status, status.replace("_", " "))
                self.samples.setItem(row, column, QTableWidgetItem(display))
            self.samples.setItem(row, 5, QTableWidgetItem(sample.updated_at))
            if sample.sample_id == select_sample:
                selected_row = row
        self.new_sample_button.setEnabled(True)
        if selected_row >= 0:
            self.samples.selectRow(selected_row)
            self._load_sample(project.project_id, samples[selected_row].sample_id)
        elif samples:
            self.samples.selectRow(0)
            self._load_sample(project.project_id, samples[0].sample_id)
        else:
            self.sample_summary.setPlainText("该项目尚无样品。")
            self.measurements.setRowCount(0)
            self.runs.setRowCount(0)
            self.current_measurement_id = None
            self.current_run_id = None
            self.current_runs = {}
            self.measurement_button.setEnabled(False)
            self._refresh_measurement_actions()
            self._refresh_run_actions()

    def _sample_selected(self):
        identifier = self._selected_id(self.samples)
        if identifier and self.current_project_id:
            self._load_sample(self.current_project_id, identifier)

    def _load_sample(self, project_id: str, sample_id: str):
        sample = self.repository.get_sample(project_id, sample_id)
        self.current_sample_id = sample.sample_id
        self.sample_summary.setPlainText(
            f"{sample.sample_id}  {sample.sample_name}\n材料体系：{sample.material_system or '未填写'}\n"
            f"批次：{sample.batch or '未填写'}    制备日期：{sample.preparation_date or '未填写'}\n"
            f"填料比例：{sample.filler_ratio or '未填写'}\n组成：{sample.composition or '未填写'}\n"
            f"处理条件：{sample.processing_conditions or '未填写'}\n备注：{sample.notes or '无'}")
        measurements = self.repository.list_measurements(project_id, sample_id)
        self.measurements.setRowCount(len(measurements))
        selected_row = -1
        for row, measurement in enumerate(measurements):
            label = MeasurementType.coerce(measurement.measurement_type).label
            item = QTableWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, measurement.measurement_id)
            self.measurements.setItem(row, 0, item)
            self.measurements.setItem(row, 1, QTableWidgetItem("\n".join(measurement.source_files)))
            self.measurements.setItem(row, 2, QTableWidgetItem(measurement.validation_status.replace("_", " ")))
            self.measurements.setItem(row, 3, QTableWidgetItem(measurement.instrument or "未填写"))
            self.measurements.setItem(row, 4, QTableWidgetItem(measurement.measurement_date or "未填写"))
            if measurement.measurement_id == self.current_measurement_id:
                selected_row = row
        self.measurement_button.setEnabled(True)
        if selected_row < 0 and measurements:
            selected_row = 0
        if selected_row >= 0:
            self.measurements.selectRow(selected_row)
            self.current_measurement_id = measurements[selected_row].measurement_id
            self._load_runs(measurements[selected_row].measurement_id)
        else:
            self.current_measurement_id = None
            self.runs.setRowCount(0)
            self.current_run_id = None
            self.current_runs = {}
        self._refresh_measurement_actions()
        self._refresh_run_actions()

    def _selected_measurement(self):
        if not (self.current_project_id and self.current_sample_id and self.current_measurement_id):
            return None
        try:
            return self.repository.get_measurement(self.current_project_id, self.current_sample_id,
                                                   self.current_measurement_id)
        except KeyError:
            return None

    def _selected_run(self):
        return self.current_runs.get(self.current_run_id or "")

    def _measurement_selected(self):
        identifier = self._selected_id(self.measurements)
        if identifier and self.current_project_id and self.current_sample_id:
            self.current_measurement_id = identifier
            self.verify_result.setText("")
            self._load_runs(identifier)
            self._refresh_measurement_actions()

    def _run_selected(self):
        identifier = self._selected_id(self.runs)
        self.current_run_id = identifier
        self._refresh_run_actions()

    def _load_runs(self, measurement_id: str):
        self.current_runs = {}
        self.current_run_id = None
        runs = self.repository.list_analysis_runs(self.current_project_id, self.current_sample_id, measurement_id) \
            if self.current_project_id and self.current_sample_id else []
        self.current_runs = {run.analysis_run_id: run for run in runs}
        self.runs.setRowCount(len(runs))
        for row, run in enumerate(runs):
            created = QTableWidgetItem(run.created_at)
            created.setData(Qt.ItemDataRole.UserRole, run.analysis_run_id)
            created.setToolTip("\n".join(run.warnings) if run.warnings else "无警告")
            self.runs.setItem(row, 0, created)
            self.runs.setItem(row, 1, QTableWidgetItem(analysis_type_label(run.analysis_type)))
            self.runs.setItem(row, 2, QTableWidgetItem(ValidationStatus.coerce(run.validation_status).label))
            self.runs.setItem(row, 3, QTableWidgetItem(str(len(run.warnings))))
            directory = run.result_refs[0] if run.result_refs else "未记录结果目录"
            self.runs.setItem(row, 4, QTableWidgetItem(directory))
        if runs:
            self.runs.selectRow(0)
            self.current_run_id = runs[0].analysis_run_id
        self._refresh_run_actions()

    def _source_paths(self, measurement) -> list[Path]:
        return [Path(item) for item in measurement.source_files] if measurement is not None else []

    def _refresh_measurement_actions(self):
        measurement = self._selected_measurement()
        kind = MeasurementType.coerce(measurement.measurement_type) if measurement is not None else None
        sources = self._source_paths(measurement)
        has_electromagnetic_source = any(path.suffix.lower() in ELECTROMAGNETIC_SOURCES for path in sources)
        has_sparameter_source = any(path.suffix.lower() == SPARAMETER_SOURCE for path in sources)
        has_vsm_source = any(path.suffix.lower() in VSM_SOURCES for path in sources)
        self.verify_button.setEnabled(measurement is not None)
        self.analyze_button.setEnabled(kind is MeasurementType.ELECTROMAGNETIC and has_electromagnetic_source)
        if kind is MeasurementType.ELECTROMAGNETIC and has_electromagnetic_source:
            self.analyze_button.setToolTip("从该测试创建一次电磁分析，完成后自动登记 AnalysisRun。")
        elif kind is MeasurementType.ELECTROMAGNETIC:
            self.analyze_button.setToolTip("该测试没有 .memp / CSV / Excel 的 ε/μ 数据文件。")
        else:
            self.analyze_button.setToolTip("该按钮只用于 Electromagnetic 测试。")
        self.sparameter_button.setEnabled(kind is MeasurementType.ELECTROMAGNETIC and has_sparameter_source)
        if kind is MeasurementType.ELECTROMAGNETIC and has_sparameter_source:
            self.sparameter_button.setToolTip("用该测试的 .sdat 创建 S 参数分析，完成后自动登记 AnalysisRun。")
        elif kind is MeasurementType.ELECTROMAGNETIC:
            self.sparameter_button.setToolTip("该测试没有 .sdat 实测文件。")
        else:
            self.sparameter_button.setToolTip("S 参数分析只接受 Electromagnetic 测试的 .sdat 文件。")
        self.vsm_button.setEnabled(kind is MeasurementType.VSM and has_vsm_source)
        if kind is MeasurementType.VSM and has_vsm_source:
            self.vsm_button.setToolTip("用该 VSM 测试的原始文件创建磁滞回线分析。")
        elif kind is MeasurementType.VSM:
            self.vsm_button.setToolTip("该测试没有 .csv / .xlsx / .xls / .txt 数据文件。")
        else:
            self.vsm_button.setToolTip("VSM 分析只接受 VSM 测试的原始文件。")

    def _refresh_run_actions(self):
        run = self._selected_run()
        available = bool(run and run.result_refs and Path(run.result_refs[0]).is_dir())
        self.open_run_button.setEnabled(available)
        self.load_run_button.setEnabled(available)

    def verify_selected_measurement(self):
        measurement = self._selected_measurement()
        if measurement is None:
            self.message.emit("请先选择一个测试。")
            return {}
        states = self.repository.verify_measurement_sources(
            self.current_project_id, self.current_sample_id, measurement.measurement_id)
        counts = {state: list(states.values()).count(state) for state in ("PASS", "CHANGED", "MISSING")}
        self.verify_result.setText(
            f"来源核验：PASS {counts['PASS']} · CHANGED {counts['CHANGED']} · MISSING {counts['MISSING']}；"
            "原始文件未被修改。")
        self.message.emit(self.verify_result.text())
        return states

    def start_measurement_analysis(self):
        """把选中的电磁测试交给电磁性能页面；不在此处复制任何科学计算。"""
        measurement = self._selected_measurement()
        if measurement is None:
            self.message.emit("请先选择一个测试。")
            return None
        if MeasurementType.coerce(measurement.measurement_type) is not MeasurementType.ELECTROMAGNETIC:
            self.message.emit("只支持从 Electromagnetic 测试开始电磁分析。")
            return None
        states = self.repository.verify_measurement_sources(
            self.current_project_id, self.current_sample_id, measurement.measurement_id)
        blocked = [(name, state) for name, state in states.items() if state != "PASS"]
        if blocked:
            QMessageBox.warning(
                self, "来源文件已变化",
                "以下原始文件与登记哈希不一致，已拒绝开始分析：\n"
                + "\n".join(f"{state}：{name}" for name, state in blocked)
                + "\n\n请恢复原始文件或重新添加测试后再分析。")
            return None
        candidates = [path for path in self._source_paths(measurement)
                      if path.suffix.lower() in ELECTROMAGNETIC_SOURCES]
        if not candidates:
            QMessageBox.information(
                self, "没有可用的 ε/μ 数据",
                "该测试没有 .memp / CSV / Excel 数据文件；实测 .sdat 请使用“用此测试开始S参数分析”。")
            return None
        path = candidates[0]
        if not path.is_file():
            QMessageBox.warning(self, "原始文件不存在", f"无法读取原始文件：{path}")
            return None
        request = {"kind": "electromagnetic_rl", "project_id": self.current_project_id,
                   "sample_id": self.current_sample_id, "measurement_id": measurement.measurement_id,
                   "path": str(path)}
        self.analysis_requested.emit(request)
        self.message.emit(f"已载入测试文件：{path.name}；在电磁性能页面确认参数后开始分析。")
        return request

    def start_measurement_sparameter_analysis(self):
        """把选中的实测 .sdat 交给 S 参数页面；不在工作区复制任何计算。"""
        measurement = self._selected_measurement()
        if measurement is None:
            self.message.emit("请先选择一个测试。")
            return None
        if MeasurementType.coerce(measurement.measurement_type) is not MeasurementType.ELECTROMAGNETIC:
            self.message.emit("S 参数分析只接受 Electromagnetic 测试。")
            return None
        states = self.repository.verify_measurement_sources(
            self.current_project_id, self.current_sample_id, measurement.measurement_id)
        blocked = [(name, state) for name, state in states.items() if state != "PASS"]
        if blocked:
            QMessageBox.warning(
                self, "来源文件已变化",
                "以下原始文件与登记哈希不一致，已拒绝开始分析：\n"
                + "\n".join(f"{state}：{name}" for name, state in blocked)
                + "\n\n请恢复原始文件或重新添加测试后再分析。")
            return None
        candidates = [path for path in self._source_paths(measurement) if path.suffix.lower() == SPARAMETER_SOURCE]
        if not candidates:
            QMessageBox.information(self, "没有 S 参数文件", "该测试没有 .sdat 实测文件。")
            return None
        path = candidates[0]
        if not path.is_file():
            QMessageBox.warning(self, "原始文件不存在", f"无法读取原始文件：{path}")
            return None
        request = {"kind": "s_parameters", "project_id": self.current_project_id,
                   "sample_id": self.current_sample_id, "measurement_id": measurement.measurement_id,
                   "path": str(path)}
        self.sparameter_analysis_requested.emit(request)
        self.message.emit(f"已载入 S 参数文件：{path.name}；在 S 参数页面确认设置后开始分析。")
        return request

    def start_measurement_vsm_analysis(self):
        """把选中的 VSM 测试交给 VSM 页面；单位和质量仍需用户显式确认。"""
        measurement = self._selected_measurement()
        if measurement is None:
            self.message.emit("请先选择一个测试。")
            return None
        if MeasurementType.coerce(measurement.measurement_type) is not MeasurementType.VSM:
            self.message.emit("VSM 分析只接受 VSM 测试。")
            return None
        states = self.repository.verify_measurement_sources(
            self.current_project_id, self.current_sample_id, measurement.measurement_id)
        blocked = [(name, state) for name, state in states.items() if state != "PASS"]
        if blocked:
            QMessageBox.warning(
                self, "来源文件已变化",
                "以下原始文件与登记哈希不一致，已拒绝开始分析：\n"
                + "\n".join(f"{state}：{name}" for name, state in blocked)
                + "\n\n请恢复原始文件或重新添加测试后再分析。")
            return None
        candidates = [path for path in self._source_paths(measurement) if path.suffix.lower() in VSM_SOURCES]
        if not candidates:
            QMessageBox.information(self, "没有 VSM 数据文件",
                                    "该测试没有 .csv / .xlsx / .xls / .txt 数据文件。")
            return None
        path = candidates[0]
        if not path.is_file():
            QMessageBox.warning(self, "原始文件不存在", f"无法读取原始文件：{path}")
            return None
        request = {"kind": "vsm_hysteresis", "project_id": self.current_project_id,
                   "sample_id": self.current_sample_id, "measurement_id": measurement.measurement_id,
                   "path": str(path)}
        self.vsm_analysis_requested.emit(request)
        self.message.emit(f"已载入 VSM 文件：{path.name}；在 VSM 页面确认单位与质量后开始分析。")
        return request

    def open_selected_run(self):
        run = self._selected_run()
        if run is None or not run.result_refs:
            self.message.emit("该运行没有记录结果目录。")
            return
        directory = Path(run.result_refs[0])
        if not directory.is_dir():
            self.message.emit(f"结果目录不存在：{directory}")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory.resolve()))):
            self.message.emit(f"无法打开结果目录：{directory}")

    def load_selected_run(self):
        run = self._selected_run()
        if run is None or not run.result_refs:
            self.message.emit("该运行没有记录结果目录。")
            return
        directory = Path(run.result_refs[0])
        if not directory.is_dir():
            self.message.emit(f"结果目录不存在：{directory}")
            return
        self.run_load_requested.emit({"directory": str(directory), "analysis_type": run.analysis_type})

    def _record_run(self, linker, project_id: str, sample_id: str, measurement_id: str,
                    directory, record):
        """登记运行并刷新样品详情；登记失败时异常向上抛出，不修改测试状态。"""
        run = linker(self._require_repository(), project_id, sample_id, measurement_id, directory, record)
        self.current_project_id = project_id
        self.current_sample_id = sample_id
        self.current_measurement_id = measurement_id
        self.current_run_id = run.analysis_run_id
        self.refresh(select_project=project_id, select_sample=sample_id)
        self.tabs.setCurrentIndex(1)
        self.message.emit(
            f"已登记分析运行 {run.analysis_run_id}；状态 {ValidationStatus.coerce(run.validation_status).label}。")
        return run

    def record_electromagnetic_run(self, project_id: str, sample_id: str, measurement_id: str,
                                   directory, record):
        """由主窗口在电磁分析成功后调用；失败时不写入运行。"""
        return self._record_run(link_electromagnetic_run, project_id, sample_id, measurement_id,
                                directory, record)

    def record_sparameter_run(self, project_id: str, sample_id: str, measurement_id: str,
                              directory, record):
        """由主窗口在 S 参数分析成功后调用；候选映射状态不会升级。"""
        return self._record_run(link_sparameter_run, project_id, sample_id, measurement_id,
                                directory, record)

    def record_vsm_run(self, project_id: str, sample_id: str, measurement_id: str,
                       directory, record):
        """由主窗口在 VSM 分析完成后调用；不可计算状态也会如实登记。"""
        return self._record_run(link_vsm_run, project_id, sample_id, measurement_id,
                                directory, record)

    def record_exports(self, result_directory, paths):
        """把显式导出的图片追加到对应运行记录；没有登记运行时不创建新记录。"""
        if self.repository is None:
            return None
        found = self.repository.find_analysis_run_by_result_directory(result_directory)
        if found is None:
            return None
        project_id, sample_id, run = found
        values = [str(item) for item in paths if str(item).strip()]
        if not values:
            return None
        updated = self.repository.add_analysis_run_export_refs(
            project_id, sample_id, run.analysis_run_id, values)
        if (project_id == self.current_project_id and sample_id == self.current_sample_id
                and run.measurement_id == self.current_measurement_id):
            self._load_runs(run.measurement_id)
        self.message.emit(f"已把 {len(values)} 个导出文件登记到分析运行 {run.analysis_run_id}。")
        return updated

    def create_project(self, name: str, **values):
        project = self._require_repository().create_project(name, **values)
        self.refresh(select_project=project.project_id)
        self.message.emit(f"已创建项目：{project.project_name}")
        return project

    def create_sample(self, name: str, **values):
        if not self.current_project_id:
            raise ValueError("请先选择项目。")
        sample = self._require_repository().create_sample(self.current_project_id, name, **values)
        self.refresh(select_project=self.current_project_id, select_sample=sample.sample_id)
        self.message.emit(f"已创建样品：{sample.sample_id}")
        return sample

    def add_measurement(self, kind: str, files, **values):
        if not self.current_project_id or not self.current_sample_id:
            raise ValueError("请先选择样品。")
        measurement = self._require_repository().add_measurement(
            self.current_project_id, self.current_sample_id, kind, files, **values)
        self.current_measurement_id = measurement.measurement_id
        self.refresh(select_project=self.current_project_id, select_sample=self.current_sample_id)
        self.tabs.setCurrentIndex(1)
        self.message.emit(f"已添加 {MeasurementType.coerce(kind).label} 测试；SHA-256 已记录。")
        return measurement

    def show_new_project(self):
        dialog = _ProjectDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.create_project(dialog.name.text(), description=dialog.description.toPlainText(),
                                    tags=_tags(dialog.tags.text()), notes=dialog.notes.toPlainText())
            except Exception as error:
                QMessageBox.critical(self, "创建失败", str(error))

    def show_new_sample(self):
        dialog = _SampleDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.create_sample(dialog.name.text(), sample_id=dialog.sample_id.text().strip() or None,
                                   material_system=dialog.material.text(), batch=dialog.batch.text(),
                                   preparation_date=dialog.preparation_date.text(), filler_ratio=dialog.filler_ratio.text(),
                                   composition=dialog.composition.toPlainText(),
                                   processing_conditions=dialog.processing.toPlainText(), tags=_tags(dialog.tags.text()),
                                   notes=dialog.notes.toPlainText())
            except Exception as error:
                QMessageBox.critical(self, "创建失败", str(error))

    def show_new_measurement(self):
        dialog = _MeasurementDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.add_measurement(dialog.kind.currentData(), dialog.files, instrument=dialog.instrument.text(),
                                     measurement_date=dialog.date.text())
            except Exception as error:
                QMessageBox.critical(self, "添加失败", str(error))
