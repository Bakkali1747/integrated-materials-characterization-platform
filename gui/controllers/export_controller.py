"""图片导出适配；使用已完成的核心结果，不接触 Qt Canvas。"""

from pathlib import Path
import os
import tempfile
from plotting.em_parameters import plot_parameters
from plotting.rl_plot import plot_rl_curve, plot_rl_2d
from plotting.style import PlotStyle, plt
from gui.controllers.analysis_controller import Cancelled


def export_figure(completed, key, path, progress, cancelled, dpi=600):
    """输入已完成结果与图类型；复用绘图 API，原子替换目标图片。"""
    path = Path(path)
    if path.suffix.lower() not in {".png", ".tiff", ".tif", ".pdf", ".svg"}:
        raise ValueError("图片格式不支持。")
    if path.resolve().is_relative_to(completed["directory"].resolve()):
        raise ValueError("不能覆盖已有分析追溯目录。")
    if cancelled():
        raise Cancelled("图片导出已取消。")
    style = PlotStyle(dpi=dpi)
    factories = {"permittivity": lambda: plot_parameters(completed["sample"], "permittivity", style),
                 "permeability": lambda: plot_parameters(completed["sample"], "permeability", style),
                 "RL_curve": lambda: plot_rl_curve(completed["curve"], style=style, threshold=completed["record"]["rl_threshold_db"]),
                 "RL_2D": lambda: plot_rl_2d(completed["result"], style)[0]}
    figure = factories[key]()
    temporary = None
    try:
        figure.suptitle("PENDING VALIDATION", fontsize=10, color="0.4")
        progress(20, "保存图片…")
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=path.suffix, delete=False) as handle:
            temporary = Path(handle.name)
        figure.savefig(temporary, dpi=dpi)
        if cancelled():
            raise Cancelled("图片导出已取消；原目标未改变。")
        os.replace(temporary, path)
        progress(100, "图片保存完成")
        return path
    finally:
        plt.close(figure)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
