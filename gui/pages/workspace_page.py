"""项目与样品工作区；只保存引用和追溯信息，不修改原始文件。"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
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
from core.common import MeasurementType, WorkspaceRepository


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

    def __init__(self, repository: WorkspaceRepository | None = None, parent=None):
        super().__init__(parent)
        self.repository = repository or WorkspaceRepository(user_data_root() / "workspace")
        self.current_project_id: str | None = None
        self.current_sample_id: str | None = None
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

        actions = QHBoxLayout()
        new_project = QPushButton("新建项目")
        new_project.setObjectName("primaryButton")
        new_project.clicked.connect(self.show_new_project)
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
        self.measurements.horizontalHeader().setStretchLastSection(True)
        sample_layout.addWidget(self.measurements, 1)
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

    def refresh(self, *, select_project: str | None = None, select_sample: str | None = None):
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
            self.new_sample_button.setEnabled(False)
            self.measurement_button.setEnabled(False)

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
            self.measurement_button.setEnabled(False)

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
        for row, measurement in enumerate(measurements):
            label = MeasurementType.coerce(measurement.measurement_type).label
            self.measurements.setItem(row, 0, QTableWidgetItem(label))
            self.measurements.setItem(row, 1, QTableWidgetItem("\n".join(measurement.source_files)))
            self.measurements.setItem(row, 2, QTableWidgetItem(measurement.validation_status.replace("_", " ")))
            self.measurements.setItem(row, 3, QTableWidgetItem(measurement.instrument or "未填写"))
            self.measurements.setItem(row, 4, QTableWidgetItem(measurement.measurement_date or "未填写"))
        self.measurement_button.setEnabled(True)

    def create_project(self, name: str, **values):
        project = self.repository.create_project(name, **values)
        self.refresh(select_project=project.project_id)
        self.message.emit(f"已创建项目：{project.project_name}")
        return project

    def create_sample(self, name: str, **values):
        if not self.current_project_id:
            raise ValueError("请先选择项目。")
        sample = self.repository.create_sample(self.current_project_id, name, **values)
        self.refresh(select_project=self.current_project_id, select_sample=sample.sample_id)
        self.message.emit(f"已创建样品：{sample.sample_id}")
        return sample

    def add_measurement(self, kind: str, files, **values):
        if not self.current_project_id or not self.current_sample_id:
            raise ValueError("请先选择样品。")
        measurement = self.repository.add_measurement(self.current_project_id, self.current_sample_id, kind, files, **values)
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
