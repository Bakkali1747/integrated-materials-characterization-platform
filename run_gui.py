r"""Windows 本地 GUI 入口：.\.venv\Scripts\python.exe run_gui.py。"""

import os
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
import sys

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))


def configure_logging():
    """写入固定项目日志目录，保留完整调试异常；轮转限制文件体积。"""
    folder = ROOT / "logs"
    folder.mkdir(exist_ok=True)
    logger = logging.getLogger("microwave.gui")
    if not logger.handlers:
        handler = RotatingFileHandler(folder / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def main():
    """建立 QApplication 与主窗口；CLI 不导入任何 Qt 依赖。"""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("缺少 GUI 依赖，请运行：.\\.venv\\Scripts\\python.exe -m pip install -r requirements-gui.txt")
        return 1
    configure_logging()
    from gui.main_window import MainWindow
    app = QApplication(sys.argv)
    app.setApplicationName("微波吸收材料分析软件")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
