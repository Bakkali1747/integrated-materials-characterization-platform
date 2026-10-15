"""RL 原始矩阵与颜色映射使用同一个数据来源，三维面不使用光照修饰。"""

import numpy as np
from matplotlib.colors import Normalize
from plotting.style import PlotStyle, new_axes
from export.origin_export import attach_grid


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
    fig.colorbar(artist, ax=ax, label="RL (dB)", ticks=np.linspace(norm.vmin, norm.vmax, 6), format="%.2f")
    ax.set(xlabel="Frequency (GHz)", ylabel="Thickness (mm)")
    attach_grid(ax, result.frequency_ghz, result.thickness_mm, result.rl_db, "RL (dB)")
    return fig, artist


def representative_thickness_indices(result, important_thicknesses=()):
    """从已计算矩阵中选最多七个均匀分布的厚度行，加入指定的关键厚度行。"""
    count = len(result.thickness_mm)
    if not count:
        raise ValueError("没有可用厚度点。")
    indices = set(np.rint(np.linspace(0, count - 1, min(7, count))).astype(int).tolist())
    for thickness in important_thicknesses:
        matches = np.flatnonzero(result.thickness_mm == thickness)
        if not len(matches):
            raise ValueError("关键厚度不在本次扫描矩阵中。")
        indices.add(int(matches[0]))
    return sorted(indices)


def plot_rl_multi_thickness(result, indices, style=None):
    """直接绘制已计算矩阵的指定行；不插值、不重新实现 RL 公式。"""
    style = style or PlotStyle()
    if not indices or any(i < 0 or i >= len(result.thickness_mm) for i in indices):
        raise ValueError("请选择有效厚度行。")
    if not np.isfinite(result.rl_db[indices]).all():
        raise ValueError("RL 含无限极限值；不截断绘图。")
    fig, ax = new_axes(style)
    for index in indices:
        ax.plot(result.frequency_ghz, result.rl_db[index], linewidth=style.linewidth,
                label=f"{result.thickness_mm[index]:.12g} mm")
    ax.axhline(-10, color="0.3", linestyle="--", linewidth=.8, label="-10 dB")
    ax.set(xlabel="Frequency (GHz)", ylabel="RL (dB)", title="Calculated reflection loss at different thicknesses")
    ax.grid(True, alpha=.18)
    ax.legend(frameon=False, ncol=2, fontsize=9)
    return fig


def plot_rl_3d(result, style=None, norm=None):
    """输入扫描结果；返回三维面和 mappable；面颜色对应四角 RL 的均值。

    rstride=cstride=1 禁止默认降采样，shade=False 保证 colorbar 与面颜色一致。
    """
    if len(result.thickness_mm) < 2:
        raise ValueError("三维面至少需要两个厚度点；可使用固定厚度曲线。")
    style = style or PlotStyle()
    norm = norm or rl_normalization(result.rl_db)
    fig, ax = new_axes(style, "3d")
    attach_grid(ax, result.frequency_ghz, result.thickness_mm, result.rl_db, "RL (dB)")
    frequency, thickness = np.meshgrid(result.frequency_ghz, result.thickness_mm)
    artist = ax.plot_surface(frequency, thickness, result.rl_db, cmap=style.cmap, norm=norm,
                             rstride=1, cstride=1, shade=False, linewidth=0, antialiased=False)
    fig.colorbar(artist, ax=ax, label="RL (dB)", shrink=0.7, pad=0.1,
                 ticks=np.linspace(norm.vmin, norm.vmax, 6), format="%.2f")
    ax.set(xlabel="Frequency (GHz)", ylabel="Thickness (mm)", zlabel="RL (dB)")
    ax.view_init(elev=25, azim=-125)
    return fig, artist
