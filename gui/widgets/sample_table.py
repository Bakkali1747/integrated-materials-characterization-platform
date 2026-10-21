from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem


class SampleTable(QTreeWidget):
    """相同目录、同名文件分组；子节点独立保存来源，避免跨目录同名误合并。"""
    source_selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(6)
        self.setHeaderLabels(["样品 / 文件", "格式", "大小", "解析 / 验证状态", "GHz", "点数"])
        self.setMinimumHeight(130)
        self.setColumnWidth(3, 200)
        self.groups, self.sources = {}, {}
        self.setSortingEnabled(True)
        self.currentItemChanged.connect(self._selected)

    def add_source(self, info):
        """输入解析摘要；更新唯一来源，绝不将 S 参数当作 ε/μ。"""
        path = info["path"]
        key = (str(path.parent).casefold(), path.stem.casefold())
        if key not in self.groups:
            self.groups[key] = QTreeWidgetItem(self, [info["sample"]])
            self.groups[key].setToolTip(0, str(path.parent))
        item = self.sources.get(path)
        if item is None:
            item = QTreeWidgetItem(self.groups[key])
            self.sources[path] = item
        frequency = info["frequency"]
        values = [path.name, info["format"], f"{info['size']:,} B" if info["size"] is not None else "—",
                  info["status"], f"{frequency[0]:g}–{frequency[1]:g}" if frequency else "—", str(info["points"] or "—")]
        for column, value in enumerate(values):
            item.setText(column, value)
            item.setToolTip(column, info.get("error", str(path)))
        item.setData(0, Qt.ItemDataRole.UserRole, info)
        self.groups[key].setExpanded(True)
        self.resizeColumnToContents(0)
        return item

    def _selected(self, item, previous):
        """只选择真实文件子节点；组节点不会继承上一次文件。"""
        self.source_selected.emit(item.data(0, Qt.ItemDataRole.UserRole) if item else None)
