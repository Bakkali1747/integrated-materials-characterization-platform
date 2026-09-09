"""RL 原始矩阵与颜色映射使用同一个数据来源，三维面不使用光照修饰。"""

import numpy as np
from matplotlib.colors import Normalize
from plotting.style import PlotStyle, new_axes


def rl_normalization(rl_db):
    """输入 RL 矩阵；返回共享归一化。非有限极限须显式处理，不能隐藏裁剪。"""
    if not np.isfinite(rl_db).all():
        raise ValueError("RL 含无限极限值；已保留数据，当前绘图不支持自动截断。")
    low, high = float(np.min(rl_db)), float(np.max(rl_db))
    if low == high:
        low, high = low - 0.5, high + 0.5
    return Normalize(vmin=low, vmax=high)


def plot_rl_curve(result, index=0, style=None, threshold=-10.0):
    """输入扫描结果与厚度行号；返回该固定厚度的 RL 曲线图。"""
    style = style or PlotStyle()
    fig, ax = new_axes(style)
    ax.plot(result.frequency_ghz, result.rl_db[index], linewidth=style.linewidth,
            label=f"d = {result.thickness_mm[index]:g} mm")
    ax.axhline(threshold, color="0.4", linestyle="--", linewidth=0.8, label=f"{threshold:g} dB")
    ax.set(xlabel="Frequency (GHz)", ylabel="RL (dB)")
    ax.legend(frameon=False)
    return fig


def plot_rl_2d(result, style=None, norm=None):
    """输入扫描结果；返回二维等高图及 mappable，矩阵行=厚度、列=频率。"""
    style = style or PlotStyle()
    norm = norm or rl_normalization(result.rl_db)
    fig, ax = new_axes(style)
    if len(result.thickness_mm) >= 2:
        artist = ax.contourf(result.frequency_ghz, result.thickness_mm, result.rl_db,
                             levels=np.linspace(norm.vmin, norm.vmax, 65), cmap=style.cmap, norm=norm)
    else:
        artist = ax.pcolormesh(result.frequency_ghz, result.thickness_mm, result.rl_db,
                               shading="nearest", cmap=style.cmap, norm=norm)
    fig.colorbar(artist, ax=ax, label="RL (dB)")
    ax.set(xlabel="Frequency (GHz)", ylabel="Thickness (mm)")
    return fig, artist


def plot_rl_3d(result, style=None, norm=None):
    """输入扫描结果；返回三维面和 mappable；面颜色对应四角 RL 的均值。

    rstride=cstride=1 禁止默认降采样，shade=False 保证 colorbar 与面颜色一致。
    """
    if len(result.thickness_mm) < 2:
        raise ValueError("三维面至少需要两个厚度点；可使用固定厚度曲线。")
    style = style or PlotStyle()
    norm = norm or rl_normalization(result.rl_db)
    fig, ax = new_axes(style, "3d")
    frequency, thickness = np.meshgrid(result.frequency_ghz, result.thickness_mm)
    artist = ax.plot_surface(frequency, thickness, result.rl_db, cmap=style.cmap, norm=norm,
                             rstride=1, cstride=1, shade=False, linewidth=0, antialiased=False)
    fig.colorbar(artist, ax=ax, label="RL (dB)", shrink=0.7, pad=0.1)
    ax.set(xlabel="Frequency (GHz)", ylabel="Thickness (mm)", zlabel="RL (dB)")
    ax.view_init(elev=25, azim=-125)
    return fig, artist
