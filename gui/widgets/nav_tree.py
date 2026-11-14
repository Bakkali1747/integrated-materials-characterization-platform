"""左侧类型化导航树；比较/批量作为各数据类型的二级入口。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem


class NavigationTree(QTreeWidget):
    page_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("nav")
        self.setHeaderHidden(True)
        self.setIndentation(14)
        self.setRootIsDecorated(True)
        self.setExpandsOnDoubleClick(False)
        self.setAnimated(False)
        self.leaves = {}
        self.children = []
        self._build()
        self.currentItemChanged.connect(self._select)

    def _add(self, label, key=None, parent=None):
        item = QTreeWidgetItem(parent or self, [label])
        if key is not None:
            item.setData(0, Qt.ItemDataRole.UserRole, key)
            self.leaves[key] = item
        else:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        return item

    def _build(self):
        self._add("首页", "home")
        self._add("工作区", "workspace")
        groups = [
            ("电磁性能", "em", ("单样品分析", "多样品比较", "批量分析")),
            ("VSM 分析", "vsm", ("单样品分析", "多样品比较", "批量分析")),
            ("XRD 分析", "xrd", ("单样品分析", "多样品比较", "批量分析")),
            ("S参数分析", "sparameter", ("单样品分析", "多样品比较", "批量分析")),
        ]
        self.groups = {}
        for label, prefix, children in groups:
            parent = self._add(label)
            self.groups[prefix] = parent
            for child_label, suffix in zip(children, ("single", "compare", "batch")):
                child = self._add(child_label, f"{prefix}.{suffix}", parent)
                if suffix != "single":
                    self.children.append(child)
            parent.setExpanded(True)
        self._add("历史结果", "history")
        self._add("设置", "settings")
        self.setCurrentItem(self.leaves["home"])

    def _select(self, current, previous):
        if current is not None:
            key = current.data(0, Qt.ItemDataRole.UserRole)
            if key:
                self.page_changed.emit(key)

    def show_page(self, key):
        item = self.leaves.get(key)
        if item is not None:
            self.setCurrentItem(item)
            self.scrollToItem(item)

    def current_page(self):
        item = self.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None

    def is_page_visible(self, key):
        item = self.leaves.get(key)
        if item is None:
            return False
        if item.isHidden():
            return False
        parent = item.parent()
        return parent is None or not parent.isHidden()

    def set_mode(self, full):
        """日常模式隐藏 S 参数及比较/批量二级入口；完整模式全部显示。"""
        self.groups["sparameter"].setHidden(not full)
        self.children = [item for item in self.children if item.parent() is not None]
        for item in self.children:
            key = item.data(0, Qt.ItemDataRole.UserRole)
            if key and key.endswith((".compare", ".batch")):
                item.setHidden(not full)
        if not full:
            key = self.current_page()
            if key and (key.startswith("sparameter.") or key.endswith((".compare", ".batch"))):
                self.show_page("home")
