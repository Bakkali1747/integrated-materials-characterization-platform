from PySide6.QtWidgets import QLabel


class StatusBadge(QLabel):
    """输入验证状态与文字；candidate/pending 永远使用黄色。"""

    def __init__(self, status="PENDING", text="验证待完成", parent=None):
        super().__init__(parent)
        self.set_status(status, text)
        self.setWordWrap(True)

    def set_status(self, status, text):
        """仅显式 validated/PASS 可显示绿色；解析成功不等于科研验证完成。"""
        self.status = status
        color = "#fbe9e7" if status in ("FAIL", "Invalid", "Parse Failed") else (
            "#e1f1e7" if status in ("validated", "PASS") else "#fff1cc")
        self.setText(f"{status}  ·  {text}")
        self.setStyleSheet(f"background: {color}; color: #283747; padding: 10px; border-radius: 4px;")
