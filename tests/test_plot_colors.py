import numpy as np
import matplotlib.pyplot as plt
from core.models import RLResult
from plotting.rl_plot import plot_rl_2d, plot_rl_3d, rl_normalization


def test_surface_actual_face_values_and_colorbar():
    matrix = np.array([[-2., -10., -20.], [-5., -25., -40.], [-7., -30., -50.]])
    result = RLResult(np.array([2, 8, 18]), np.array([1, 2, 3]), matrix, np.zeros_like(matrix, dtype=complex))
    norm = rl_normalization(matrix)
    fig2, artist2 = plot_rl_2d(result, norm=norm)
    fig3, artist3 = plot_rl_3d(result, norm=norm)
    expected = (matrix[:-1, :-1]+matrix[1:, :-1]+matrix[:-1, 1:]+matrix[1:, 1:])/4
    np.testing.assert_allclose(artist3.get_array(), expected.ravel())
    assert artist2.norm is artist3.norm is norm
    assert artist2.colorbar.mappable is artist2 and artist3.colorbar.mappable is artist3
    assert norm.vmin == -50 and norm.vmax == -2
    np.testing.assert_array_equal(artist2.colorbar.get_ticks(), artist3.colorbar.get_ticks())
    fig3.canvas.draw()
    # 内部 facecolors 保持面输入顺序，公开 get_facecolors 会按深度排序。
    np.testing.assert_allclose(artist3._facecolor3d, artist3.cmap(norm(expected.ravel())))
    assert artist2.levels[0] == -50 and artist2.levels[-1] == -2
    plt.close(fig2)
    plt.close(fig3)
