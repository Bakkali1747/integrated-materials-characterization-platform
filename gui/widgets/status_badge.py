from PySide6.QtWidgets import QLabel


class StatusBadge(QLabel):
    """输入验证状态与文字；candidate/pending 永远使用黄色。"""

    STYLES = {
        "error": ("background: #FEF2F2; color: #991B1B; border: 1px solid #FECACA;"
                  " border-left: 4px solid #EF4444;"),
        "ok": ("background: #ECFDF5; color: #065F46; border: 1px solid #A7F3D0;"
               " border-left: 4px solid #10B981;"),
        "pending": ("background: #FFFBEB; color: #7C4A03; border: 1px solid #FDE68A;"
                    " border-left: 4px solid #F59E0B;"),
    }

    def __init__(self, status="PENDING", text="验证待完成", parent=None):
        super().__init__(parent)
        self.set_status(status, text)
        self.setWordWrap(True)

    def set_status(self, status, text):
        """仅显式 validated/PASS 可显示绿色；解析成功不等于科研验证完成。"""
        self.status = status
        kind = "error" if status in ("FAIL", "Invalid", "Parse Failed") else (
            "ok" if status in ("validated", "PASS") else "pending")
        self.setText(f"{status}  ·  {text}")
        self.setStyleSheet(
            f"{self.STYLES[kind]} padding: 9px 12px; border-radius: 8px; font-size: 9pt;")
