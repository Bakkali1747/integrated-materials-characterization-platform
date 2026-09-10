from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QFileDialog


class FileSelector(QWidget):
    """文件、多选和文件夹入口；拖拽由主窗口统一接收。"""
    files_selected = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        self.files_button = QPushButton("选择文件（可多选）")
        self.folder_button = QPushButton("选择文件夹")
        layout.addWidget(self.files_button)
        layout.addWidget(self.folder_button)
        self.files_button.clicked.connect(self.choose_files)
        self.folder_button.clicked.connect(self.choose_folder)

    def choose_files(self):
        """返回用户选中的路径；取消选择时不触发导入。"""
        paths, _ = QFileDialog.getOpenFileNames(self, "导入科研数据", "", "科研数据 (*.memp *.sdat *.csv *.xlsx *.xls);;所有文件 (*)")
        if paths:
            self.files_selected.emit(paths)

    def choose_folder(self):
        """返回目录路径；扫描放入后台，保持主线程可响应。"""
        path = QFileDialog.getExistingDirectory(self, "选择数据文件夹")
        if path:
            self.files_selected.emit([path])
