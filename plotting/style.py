"""所有绘图共享科研风格和尺寸。"""

from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: F401  (re-exported for plotting/GUI modules)
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure


@dataclass
class PlotStyle:
    width: float = 7.0
    height: float = 4.8
    linewidth: float = 1.5
    cmap: str = "viridis"
    dpi: int = 600


def new_figure(style=None):
    """返回未注册到 pyplot 全局表的 Figure；后台线程不再争用 Gcf 状态。"""
    style = style or PlotStyle()
    figure = Figure(figsize=(style.width, style.height), layout="constrained")
    FigureCanvasAgg(figure)
    return figure


def new_axes(style=None, projection=None):
    """输入绘图配置和可选 3d 投影；返回 figure/axes，不改变计算数据。"""
    style = style or PlotStyle()
    with matplotlib.rc_context({"font.size": 11, "axes.labelsize": 11, "axes.linewidth": 0.8}):
        figure = new_figure(style)
        axes = figure.add_subplot(111, projection=projection)
    return figure, axes
