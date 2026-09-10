"""可排序的结果快照；仅同网格比较高亮 RLmin/EAB 的全部并列最佳值。"""
import math
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QAbstractItemView


class NumericItem(QTableWidgetItem):
    def __lt__(self, other):
        left, right = self.data(Qt.ItemDataRole.UserRole), other.data(Qt.ItemDataRole.UserRole)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left < right
        return super().__lt__(other)


class MetricsTable(QTableWidget):
    COLUMNS = [("sample", "样品"), ("status", "状态"), ("rl_min_db", "RLmin (dB)"),
        ("rl_min_frequency_ghz", "RLmin 频率 (GHz)*"), ("best_thickness_mm", "最佳厚度 (mm)*"),
        ("maximum_eab_ghz", "Maximum EAB (GHz)"), ("maximum_eab_frequency_ranges_ghz", "EAB 频段 (GHz)*"),
        ("thickness_at_maximum_eab_mm", "EAB 厚度 (mm)*"), ("rl_min_tie_count", "RLmin 并列点数"),
        ("maximum_eab_thickness_tie_count", "EAB 并列厚度数"), ("frequency_min_ghz", "频率起点"),
        ("frequency_max_ghz", "频率终点"), ("validation", "验证状态")]

    def __init__(self):
        super().__init__()
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(True)

    def load_rows(self, rows, comparable):
        """显示已有摘要，不计算新的科学指标；无数据不填零。"""
        self.setSortingEnabled(False)
        self.clear()
        self.setColumnCount(len(self.COLUMNS)); self.setRowCount(len(rows))
        self.setHorizontalHeaderLabels([label for key, label in self.COLUMNS])
        for index in range(len(self.COLUMNS)):
            self.setColumnWidth(index, 155)
        best = {}
        if comparable:
            for key, reducer in (("rl_min_db", min), ("maximum_eab_ghz", max)):
                values = [row[key] for row in rows if row.get("status") == "success" and row.get(key) is not None]
                if values:
                    best[key] = reducer(values)
        for i, row in enumerate(rows):
            for j, (key, label) in enumerate(self.COLUMNS):
                value = row.get(key)
                item = NumericItem("—" if value is None else f"{value:.8g}" if isinstance(value, float) else str(value))
                item.setData(Qt.ItemDataRole.UserRole, value)
                item.setToolTip(str(row.get("error", value if value is not None else "无有效结果")))
                if key in best and isinstance(value, (int, float)) and (value == best[key] or math.isclose(value, best[key], rel_tol=0, abs_tol=1e-12)):
                    item.setBackground(QColor("#e5eef8"))
                self.setItem(i, j, item)
        self.setSortingEnabled(True)
