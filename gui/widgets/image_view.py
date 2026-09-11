"""随可用区域缩放已保存图片，不产生新的科研图。"""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy


class ImageView(QLabel):
    def __init__(self):
        super().__init__("选择已保存图片")
        self.original = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

    def clear(self):
        self.original = QPixmap()
        super().clear()

    def set_image(self, pixmap):
        self.original = pixmap
        self.refresh()

    def sizeHint(self):
        return QSize(500,400)

    def refresh(self):
        if not self.original.isNull():
            super().setPixmap(self.original.scaled(self.contentsRect().size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh()
