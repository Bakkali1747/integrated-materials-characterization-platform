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
    font_size: float = 11
    palette: tuple | None = None


COLORBLIND = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9")


def style_for(preset="screen", dpi=600):
    """输入 screen/single/double；返回对应尺寸与字号的 PlotStyle。"""
    if preset == "single":
        return PlotStyle(width=3.5, height=2.6, dpi=dpi, font_size=8, palette=COLORBLIND)
    if preset == "double":
        return PlotStyle(width=7.0, height=4.0, dpi=dpi, font_size=9, palette=COLORBLIND)
    if preset not in (None, "screen"):
        raise ValueError("图样式必须为 screen、single 或 double。")
    return PlotStyle(dpi=dpi)


def journal_style(kind="single", dpi=600):
    """期刊单栏/双栏尺寸的便捷入口。"""
    return style_for(kind, dpi)


def new_figure(style=None):
    """返回未注册到 pyplot 全局表的 Figure；后台线程不再争用 Gcf 状态。"""
    style = style or PlotStyle()
    figure = Figure(figsize=(style.width, style.height), layout="constrained")
    FigureCanvasAgg(figure)
    return figure


def new_axes(style=None, projection=None):
    """输入绘图配置和可选 3d 投影；返回 figure/axes，不改变计算数据。"""
    style = style or PlotStyle()
    settings = {"font.size": style.font_size, "axes.labelsize": style.font_size,
                "axes.linewidth": 0.8, "xtick.labelsize": style.font_size - 1,
                "ytick.labelsize": style.font_size - 1}
    if style.palette:
        settings["axes.prop_cycle"] = matplotlib.cycler(color=style.palette)
    with matplotlib.rc_context(settings):
        figure = new_figure(style)
        axes = figure.add_subplot(111, projection=projection)
    return figure, axes
