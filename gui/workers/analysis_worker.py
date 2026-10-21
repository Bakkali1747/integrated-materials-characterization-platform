"""QThread 执行有界任务；取消不会强制终止线程或损坏正在写入的结果。"""

import logging

from PySide6.QtCore import QThread, Signal

from gui.controllers.analysis_controller import Cancelled


class AnalysisWorker(QThread):
    progress = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal(str)

    def __init__(self, operation, parent=None):
        """输入 operation(progress, cancelled)；信号返回结果或简明错误。"""
        super().__init__(parent)
        self.operation = operation

    def run(self):
        """在后台执行；完整异常写日志，不把 traceback 交给普通用户。"""
        try:
            result = self.operation(self.progress.emit, self.isInterruptionRequested)
            self.succeeded.emit(result)
        except Cancelled as error:
            self.cancelled.emit(str(error))
        except Exception as error:
            logging.getLogger("microwave.gui").exception("后台任务失败")
            self.failed.emit(f"错误类型：{type(error).__name__}\n具体问题：{error}\n"
                             "建议：检查源文件、列映射、单位、厚度范围及输出目录权限；缺失值请修正原始数据。\n"
                             "完整诊断已记录到 logs/app.log。")
