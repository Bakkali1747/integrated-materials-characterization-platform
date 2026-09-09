"""复数表示只在这一层构造，避免重复添加虚部负号。"""

import numpy as np


def make_complex(real, loss_imag):
    """输入相对参数实部及损耗系数；返回同形状 real - j*loss_imag。

    输入均无量纲；负损耗系数保留，不能通过 abs 伪造被动性。
    """
    real, loss_imag = np.asarray(real, dtype=float), np.asarray(loss_imag, dtype=float)
    if real.shape != loss_imag.shape or not np.isfinite(real).all() or not np.isfinite(loss_imag).all():
        raise ValueError("实部/损耗虚部必须同形状且全部有限。")
    return real - 1j * loss_imag
