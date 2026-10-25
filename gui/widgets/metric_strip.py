"""结果页顶部的关键指标卡；只读取已完成运行的摘要，不重新计算。"""

import math

from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget


def _number(value, digits=2, suffix=""):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(value):
        return "—"
    return f"{value:.{digits}f}{suffix}"


class MetricCard(QFrame):
    """一个指标：标题、主数值、上下文说明。"""

    def __init__(self, caption, parent=None):
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setAccessibleName(caption)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        self.caption = QLabel(caption)
        self.caption.setObjectName("metricCaption")
        self.value = QLabel("—")
        self.value.setObjectName("metricValue")
        self.detail = QLabel("")
        self.detail.setObjectName("metricDetail")
        self.detail.setWordWrap(True)
        layout.addWidget(self.caption)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set_metric(self, value, detail="", tooltip=""):
        self.value.setText(value)
        self.detail.setText(detail)
        self.setToolTip(tooltip)
        self.value.setToolTip(tooltip)


class MetricStrip(QWidget):
    """最小 RL / 最大 EAB / 当前厚度 RL / 当前厚度 EAB。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)
        self.cards = [
            MetricCard("最小 RL"),
            MetricCard("最大 EAB"),
            MetricCard("当前厚度 RL"),
            MetricCard("当前厚度 EAB"),
        ]
        for index, card in enumerate(self.cards):
            grid.addWidget(card, index // 2, index % 2)
        self.hide()

    def update_from_summary(self, summary, record):
        minima = list(summary.get("global_minima") or [])
        best = min((item for item in minima if _is_finite(item.get("rl_min_db"))),
                   key=lambda item: item["rl_min_db"], default={})
        if best:
            detail = f"{_number(best.get('frequency_ghz'), 2)} GHz · {_number(best.get('thickness_mm'), 2)} mm"
            ties = f"全部 {len(minima)} 个并列最小点见下方摘要。" if len(minima) > 1 else "全部并列点见下方摘要。"
            self.cards[0].set_metric(_number(best.get("rl_min_db"), 2, " dB"), detail, ties)
        else:
            self.cards[0].set_metric("—", "无有限 RL 最小值")

        eab = summary.get("standard_eab") or {}
        best_thicknesses = eab.get("best_thicknesses") or []
        detail = "−10 dB 连续带宽"
        if best_thicknesses:
            detail = f"最优 {_number(best_thicknesses[0].get('thickness_mm'), 2)} mm" + (
                f" · 共 {len(best_thicknesses)} 个厚度并列" if len(best_thicknesses) > 1 else "")
        self.cards[1].set_metric(_number(eab.get("maximum_bandwidth_ghz"), 2, " GHz"), detail,
                                 "EAB 为最长连续频带，不把分离频段相加。")

        curve = (summary.get("curve_minima") or [{}])[0]
        curve_thickness = record.get("configuration", {}).get("curve_thickness_mm")
        self.cards[2].set_metric(_number(curve.get("rl_min_db"), 2, " dB"),
                                 f"曲线厚度 {_number(curve_thickness, 2)} mm")

        curve_eab = summary.get("curve_standard_eab") or {}
        self.cards[3].set_metric(_number(curve_eab.get("maximum_continuous_bandwidth_ghz"), 2, " GHz"),
                                 "当前厚度 · 连续带宽",
                                 "当前指定厚度下的最长连续 −10 dB 频带。")
        self.show()


def _is_finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False
