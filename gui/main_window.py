"""综合材料表征分析平台主窗口。"""

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core import __version__
from gui.controllers.settings_controller import SettingsStore
from gui.pages.batch_page import BatchPage
from gui.pages.comparison_page import ComparisonPage
from gui.pages.home_page import HomePage
from gui.pages.results_page import ResultsPage
from gui.pages.settings_page import SettingsPage
from gui.pages.single_sample_page import SingleSamplePage
from gui.pages.sparameter_page import SParameterPage
from gui.pages.vsm_page import VsmPage
from gui.pages.workspace_page import WorkspacePage
from gui.pages.xrd_page import XrdPage
from gui.theme import apply_theme


class MainWindow(QMainWindow):
    def __init__(self, settings_store=None, workspace_repository=None):
        super().__init__()
        apply_theme(QApplication.instance())
        self.setWindowTitle(f"综合材料表征分析平台 · v{__version__} · Phase B")
        self.resize(1400, 900)
        self.setMinimumSize(1200, 750)
        self.setAcceptDrops(True)
        body = QWidget()
        body.setObjectName("appRoot")
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(6, 20, 6, 10)
        side_layout.setSpacing(4)
        brand = QLabel("材料表征平台")
        brand.setObjectName("brandTitle")
        brand_sub = QLabel("MATERIALS CHARACTERIZATION")
        brand_sub.setObjectName("brandSub")
        version = QLabel(f"v{__version__}")
        version.setObjectName("brandBadge")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setMaximumWidth(64)
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(12, 0, 8, 0)
        brand_row.addWidget(brand)
        brand_row.addStretch()
        brand_row.addWidget(version)
        side_layout.addLayout(brand_row)
        brand_hint = QLabel("LOCAL SCIENTIFIC ANALYSIS")
        brand_hint.setObjectName("brandSub")
        brand_hint.setContentsMargins(12, 0, 0, 8)
        self.mode_hint = brand_hint
        side_layout.addWidget(brand_hint)
        work = QLabel("工作区")
        work.setObjectName("sideSection")
        side_layout.addWidget(work)
        self.navigation = QListWidget()
        self.navigation.setObjectName("nav")
        self.navigation.setFrameShape(QFrame.Shape.NoFrame)
        self.navigation.addItems(["首页", "工作区", "电磁性能", "VSM 分析", "XRD 分析", "S参数分析", "多样品比较", "批量分析", "历史结果", "设置"])
        side_layout.addWidget(self.navigation, 1)
        footer = QLabel("本地计算 · 数据不外传\n缺失数据插值 OFF")
        footer.setObjectName("sideFooter")
        footer.setWordWrap(True)
        self.side_footer = footer
        side_layout.addWidget(footer)
        layout.addWidget(sidebar)
        self.stack = QStackedWidget()
        self.home = HomePage()
        self.workspace = WorkspacePage(workspace_repository)
        self.single = SingleSamplePage()
        self.stack.addWidget(self.home)
        self.stack.addWidget(self.workspace)
        self.stack.addWidget(self.single)
        self.vsm = VsmPage()
        self.stack.addWidget(self.vsm)
        self.xrd = XrdPage()
        self.stack.addWidget(self.xrd)
        self.sparameters = SParameterPage()
        self.comparison = ComparisonPage()
        self.stack.addWidget(self.sparameters)
        self.stack.addWidget(self.comparison)
        self.batch = BatchPage()
        self.history = ResultsPage()
        self.stack.addWidget(self.batch)
        self.stack.addWidget(self.history)
        self.task_pages = [self.single, self.vsm, self.xrd, self.sparameters, self.comparison, self.batch, self.history]
        from gui.widgets.mapping_dialog import configure_mapping
        for page in (self.single,self.comparison,self.batch):
            page.parameters.mapping_button.clicked.connect(lambda checked=False,p=page:configure_mapping(p,p.parameters))
        for page in (self.comparison,self.batch):
            page.parameters.quick_preview.hide()
        for page in (self.comparison,):
            page.parameters.reuse.hide()
        self.single.analysis_completed.connect(self.sparameters.add_theory)
        self.single.analysis_completed.connect(lambda r: self.comparison.add_source(r["record"]["raw_file"], r["sample"].name))
        self.single.table.source_selected.connect(self.transfer_source)
        for page in self.task_pages:
            page.busy_changed.connect(self.update_task_lock)
            page.message.connect(self.statusBar().showMessage)
        self.settings_store = settings_store or SettingsStore()
        self.settings = SettingsPage()
        self.stack.addWidget(self.settings)
        self.settings.apply_requested.connect(self.save_settings)
        preferences, settings_warning = self.settings_store.load()
        self.apply_preferences(preferences)
        self.settings.message.setText(settings_warning)
        content = QWidget()
        content.setObjectName("contentHost")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 18, 22, 16)
        content_layout.addWidget(self.stack)
        layout.addWidget(content, 1)
        self.setCentralWidget(body)
        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.home.navigate.connect(self.navigation.setCurrentRow)
        self.workspace.message.connect(self.statusBar().showMessage)
        self.single.message.connect(self.statusBar().showMessage)
        self.pending_workspace_analysis = None
        self.workspace.analysis_requested.connect(self.start_workspace_analysis)
        self.workspace.sparameter_analysis_requested.connect(self.start_workspace_sparameter_analysis)
        self.workspace.vsm_analysis_requested.connect(self.start_workspace_vsm_analysis)
        self.workspace.xrd_analysis_requested.connect(self.start_workspace_xrd_analysis)
        self.workspace.run_load_requested.connect(self.open_workspace_run)
        self.single.analysis_completed.connect(self.record_workspace_analysis)
        self.single.exports_saved.connect(self.record_workspace_exports)
        self.sparameters.analysis_completed.connect(self.record_workspace_sparameter_run)
        self.sparameters.exports_saved.connect(self.record_workspace_exports)
        self.vsm.analysis_completed.connect(self.record_workspace_vsm_run)
        self.vsm.exports_saved.connect(self.record_workspace_exports)
        self.xrd.analysis_completed.connect(self.record_workspace_xrd_run)
        self.xrd.exports_saved.connect(self.record_workspace_exports)
        self.navigation.setCurrentRow(0)
        self.statusBar().showMessage("就绪 · 缺失数据插值 OFF · 真实数据验证 PENDING")
        if settings_warning:
            self.statusBar().showMessage(settings_warning)

    def apply_preferences(self, values):
        self.settings.populate(values)
        for page in (self.single, self.comparison, self.batch):
            page.parameters.apply_defaults(values)
        self.sparameters.output.setText(values["output"])
        self.vsm.output.setText(values["output"])
        self.xrd.output.setText(values["output"])
        for page in self.task_pages:
            # 交互分析按设置 DPI；手动导出至少 600 dpi，便于投稿和印刷。
            page.export_dpi = max(600, values["dpi"])
            page.figure_format = values["figure_format"]
        self.set_ui_mode(values.get("ui_mode", "simple"))

    def set_ui_mode(self, mode):
        """日常模式隐藏 S 参数/比较/批量；VSM 与 XRD 作为主流程始终可用。"""
        simple = mode != "full"
        self.ui_mode = mode
        self.mode_hint.setText("DAILY WORKSPACE" if simple else "FULL WORKSPACE")
        self.side_footer.setText(
            ("日常模式 · 工作区 / 电磁 / VSM / XRD / 历史" if simple else "完整功能 · 含 S 参数 / 比较 / 批量")
            + "\n本地计算 · 数据不外传")
        for row in (5, 6, 7):
            self.navigation.setRowHidden(row, simple)
        self.home.set_simple(simple)
        for page in (self.single, self.comparison, self.batch):
            page.parameters.set_simple(simple)
        self.single.set_simple(simple)
        self.history.set_simple(simple)
        if simple and self.navigation.currentRow() in (5, 6, 7):
            self.navigation.setCurrentRow(0)

    def save_settings(self, values):
        if any(page.busy for page in self.task_pages):
            self.settings.message.setText("任务运行中，结束后可应用默认设置。")
            return
        try:
            saved = self.settings_store.save(values)
            self.apply_preferences(saved)
            self.settings.message.setText("已保存并应用；参数修改不自动计算。更改单位后请重新导入检查。")
        except Exception as error:
            import logging
            logging.getLogger("microwave.gui").exception("设置保存失败")
            self.settings.message.setText(f"保存失败，参数未应用：{error}")

    def start_workspace_analysis(self, request):
        """工作区测试 → 电磁页面；只准备文件和上下文，分析仍由用户显式触发。"""
        if any(page.busy for page in self.task_pages):
            self.statusBar().showMessage("当前任务运行中，请完成或取消后再开始工作区分析。")
            return
        self.pending_workspace_analysis = dict(request)
        self.navigation.setCurrentRow(2)
        self.single.import_paths([request["path"]])
        self.statusBar().showMessage(
            f"已载入工作区测试文件：{Path(request['path']).name}；确认参数后点击“开始分析”，完成后自动登记运行。")

    def record_workspace_analysis(self, result):
        """电磁分析成功后登记 AnalysisRun；来源哈希、类型与状态由核心模块校验。"""
        return self._record_workspace_result(
            result, "electromagnetic_rl",
            lambda context, payload: self.workspace.record_electromagnetic_run(
                context["project_id"], context["sample_id"], context["measurement_id"],
                payload["directory"], payload["record"]))

    def start_workspace_sparameter_analysis(self, request):
        """工作区实测 .sdat → S 参数页面；只在用户点击后开始计算。"""
        if any(page.busy for page in self.task_pages):
            self.statusBar().showMessage("当前任务运行中，请完成或取消后再开始 S 参数分析。")
            return
        if self.ui_mode != "full":
            self.set_ui_mode("full")
        self.pending_workspace_analysis = dict(request)
        self.navigation.setCurrentRow(5)
        self.sparameters.file.setText(request["path"])
        self.sparameters.name.setText(Path(request["path"]).stem)
        self.sparameters.error.clear()
        self.statusBar().showMessage(
            f"已载入工作区 S 参数文件：{Path(request['path']).name}；确认设置后点击“开始 S 参数分析”。")

    def record_workspace_sparameter_run(self, result):
        """S 参数分析成功后登记 AnalysisRun；候选映射状态不会被升级。"""
        return self._record_workspace_result(
            result, "s_parameters",
            lambda context, payload: self.workspace.record_sparameter_run(
                context["project_id"], context["sample_id"], context["measurement_id"],
                payload["directory"], payload["record"]))

    def start_workspace_vsm_analysis(self, request):
        """工作区 VSM 测试 → VSM 页面；单位与质量仍由用户确认。"""
        if any(page.busy for page in self.task_pages):
            self.statusBar().showMessage("当前任务运行中，请完成或取消后再开始 VSM 分析。")
            return
        self.pending_workspace_analysis = dict(request)
        self.navigation.setCurrentRow(3)
        self.vsm.file.setText(request["path"])
        self.vsm.name.setText(Path(request["path"]).stem)
        self.vsm.error.clear()
        self.vsm.load_columns()
        self.statusBar().showMessage(
            f"已载入工作区 VSM 文件：{Path(request['path']).name}；确认单位与质量后点击“开始 VSM 分析”。")

    def record_workspace_vsm_run(self, result):
        """VSM 分析完成后登记 AnalysisRun；不可计算状态也会如实登记。"""
        return self._record_workspace_result(
            result, "vsm_hysteresis",
            lambda context, payload: self.workspace.record_vsm_run(
                context["project_id"], context["sample_id"], context["measurement_id"],
                payload["directory"], payload["record"]))

    def start_workspace_xrd_analysis(self, request):
        """工作区 XRD 测试 → XRD 页面；波长与峰参数仍由用户确认。"""
        if any(page.busy for page in self.task_pages):
            self.statusBar().showMessage("当前任务运行中，请完成或取消后再开始 XRD 分析。")
            return
        self.pending_workspace_analysis = dict(request)
        self.navigation.setCurrentRow(4)
        self.xrd.file.setText(request["path"])
        self.xrd.name.setText(Path(request["path"]).stem)
        self.xrd.error.clear()
        self.xrd.load_columns()
        self.statusBar().showMessage(
            f"已载入工作区 XRD 文件：{Path(request['path']).name}；确认波长与峰参数后点击“开始 XRD 分析”。")

    def record_workspace_xrd_run(self, result):
        """XRD 分析完成后登记 AnalysisRun；未检测到峰时登记 NOT_COMPUTABLE。"""
        return self._record_workspace_result(
            result, "xrd_peaks",
            lambda context, payload: self.workspace.record_xrd_run(
                context["project_id"], context["sample_id"], context["measurement_id"],
                payload["directory"], payload["record"]))

    def _record_workspace_result(self, result, kind, register):
        """统一校验待登记上下文与源文件，再交给页面登记；失败不写入运行。"""
        context = self.pending_workspace_analysis
        if not context or context.get("kind") != kind:
            return None
        raw_file = str(result["record"].get("raw_file") or "")
        same = (bool(raw_file)
                and Path(raw_file).expanduser().resolve() == Path(context["path"]).expanduser().resolve())
        if not same:
            self.pending_workspace_analysis = None
            self.statusBar().showMessage("本次分析文件与工作区测试不一致；未登记 AnalysisRun。")
            return None
        run = None
        try:
            run = register(context, result)
        except Exception as error:
            logging.getLogger("microwave.gui").exception("登记工作区分析运行失败")
            self.statusBar().showMessage(f"分析已完成，但登记工作区运行失败：{error}")
        else:
            self.statusBar().showMessage(
                f"分析运行已登记到工作区：{run.analysis_run_id}（{run.validation_status}）。")
        finally:
            self.pending_workspace_analysis = None
        return run

    def open_workspace_run(self, payload):
        """按运行类型载入已登记结果；只读取保存产物，不重新计算。"""
        if any(page.busy for page in self.task_pages):
            self.statusBar().showMessage("当前任务运行中，请稍后再载入工作区运行。")
            return
        if isinstance(payload, str):
            payload = {"directory": payload}
        directory = payload.get("directory")
        analysis_type = payload.get("analysis_type")
        if not directory:
            return
        if analysis_type == "s_parameters":
            if self.ui_mode != "full":
                self.set_ui_mode("full")
            self.navigation.setCurrentRow(5)
            self.sparameters.open_completed_run(directory)
        elif analysis_type == "vsm_hysteresis":
            self.navigation.setCurrentRow(3)
            self.vsm.open_completed_run(directory)
        elif analysis_type == "xrd_peaks":
            self.navigation.setCurrentRow(4)
            self.xrd.open_completed_run(directory)
        else:
            self.navigation.setCurrentRow(2)
            self.single.open_completed_run(directory)

    def record_workspace_exports(self, payload):
        """把显式导出的图片追加到对应 AnalysisRun；没有登记运行时不新建记录。"""
        if not isinstance(payload, dict):
            return
        paths = [str(item) for item in payload.get("paths") or [] if str(item).strip()]
        if payload.get("directory") and paths:
            self.workspace.record_exports(payload["directory"], paths)

    def dragEnterEvent(self, event):
        """只接收本地文件 URL；分析运行中不接受新的拖入。"""
        if not any(p.busy for p in self.task_pages) and event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        """拖拽复用与文件对话框相同的导入路径。"""
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths and not any(p.busy for p in self.task_pages):
            self.navigation.setCurrentRow(2)
            self.single.import_paths(paths)
            event.acceptProposedAction()

    def closeEvent(self, event):
        """不销毁运行中的 QThread；先请求取消，让用户在任务结束后关闭。"""
        if any(p.busy for p in self.task_pages):
            for page in self.task_pages:
                if page.busy:
                    page.cancel()
            self.statusBar().showMessage("正在安全结束后台任务；结束后可再次关闭窗口。")
            event.ignore()
        else:
            event.accept()

    def update_task_lock(self, *_):
        """跨页面串行运行 pyplot 任务，其他页面可导航但不能并发操作。"""
        active = next((p for p in self.task_pages if p.busy), None)
        for page in self.task_pages:
            page.setEnabled(active is None or page is active)
        self.settings.setEnabled(active is None)

    def transfer_source(self, info):
        """已选 SDAT 传给独立页面；不自动把它送入材料计算。"""
        if info and info["format"] == ".sdat":
            self.sparameters.file.setText(str(info["path"]))
            self.sparameters.name.setText(info["sample"])
