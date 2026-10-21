r"""Windows 本地 GUI 入口：.\.venv\Scripts\python.exe run_gui.py。"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from application_paths import user_data_root

ROOT = user_data_root()
if getattr(sys, "frozen", False):
    os.environ["MPLCONFIGDIR"] = str(ROOT / ".mplconfig")
else:
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))


def configure_logging():
    """写入固定项目日志目录，保留完整调试异常；轮转限制文件体积。"""
    folder = ROOT / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("microwave.gui")
    if not logger.handlers:
        handler = RotatingFileHandler(folder / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def install_error_reporting():
    """把未捕获异常与 Qt 消息写入 app.log，避免槽函数异常只落在 stderr。"""
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    logger = logging.getLogger("microwave.gui")

    def hook(kind, value, tb):
        if issubclass(kind, KeyboardInterrupt):
            sys.__excepthook__(kind, value, tb)
            return
        logger.error("未捕获异常", exc_info=(kind, value, tb))
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                QMessageBox.critical(None, "程序错误",
                                     f"{kind.__name__}: {value}\n\n详细信息已写入日志：{ROOT / 'logs/app.log'}")
        except Exception:
            pass

    def qt_message(mode, context, message):
        level = logging.DEBUG if mode == QtMsgType.QtDebugMsg else logging.WARNING
        logger.log(level, "Qt: %s", message)

    sys.excepthook = hook
    qInstallMessageHandler(qt_message)


def main():
    """建立 QApplication 与主窗口；CLI 不导入任何 Qt 依赖。"""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as error:
        configure_logging()
        logging.getLogger("microwave.gui").exception("Qt 运行库加载失败")
        message = f"Qt 运行库加载失败：{error}\n请重新安装客户端；源码环境请安装 requirements-gui.txt。\n日志：{ROOT / 'logs/app.log'}"
        if getattr(sys, "frozen", False) and "--self-test" not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "启动失败", 0x10)
        elif sys.stderr is not None:
            print(message, file=sys.stderr)
        return 1
    app = QApplication(sys.argv)
    app.setApplicationName("微波吸收材料分析软件")
    app.setStyle("Fusion")
    try:
        configure_logging()
        install_error_reporting()
        if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
            from gui.packaging_smoke import run_smoke
            return run_smoke(app, Path(sys.argv[2]))
        from gui.main_window import MainWindow
        window = MainWindow()
    except Exception as error:
        logging.getLogger("microwave.gui").exception("客户端启动失败")
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "启动失败", f"无法启动客户端：{error}\n日志目录：{ROOT / 'logs'}")
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
