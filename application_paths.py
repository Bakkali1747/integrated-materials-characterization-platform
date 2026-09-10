"""源码和安装版路径；用户数据不写入程序安装目录。"""

import os
import sys
from pathlib import Path


def resource_root():
    """返回只读程序资源根目录；冻结版使用 PyInstaller 资源目录。"""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def user_data_root():
    """源码运行保持项目目录；安装版使用当前用户 LocalAppData。"""
    if getattr(sys, "frozen", False):
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "MicrowaveAbsorptionAnalyzer"
    return Path(__file__).resolve().parent
