import matplotlib.pyplot as plt
import numpy as np

from core.mechanism import mechanism_parameters
from core.models import RLResult, SampleData
from plotting.impedance_plot import plot_impedance_2d, plot_impedance_curve
from plotting.mechanism_plot import plot_quarter_wave_overlay


def test_impedance_color_range_and_curve():
    z = np.array([[.5+.5j, 1+1j, 2+1j], [.3+.2j, 1+0j, 1.5+.7j]])
    result = RLResult(np.array([2, 3, 4]), np.array([1, 2]), np.ones((2, 3))*-5, z)
    fig, artist = plot_impedance_2d(result)
    assert artist.norm.vmin == abs(z).min() and artist.norm.vmax == abs(z).max()
    assert artist.colorbar.mappable is artist
    curve = plot_impedance_curve(result)
    np.testing.assert_allclose(curve.axes[0].lines[0].get_ydata(), abs(z[0]))
    np.testing.assert_allclose(curve.axes[0].lines[1].get_ydata(), z[0].real)
    np.testing.assert_allclose(curve.axes[0].lines[2].get_ydata(), z[0].imag)
    plt.close(fig)
    plt.close(curve)


def test_overlay_keeps_scanned_thickness_limits(frame):
    table, _ = mechanism_parameters(SampleData("synthetic", frame, {}), (1, 3))
    result = RLResult(np.array([2, 3, 4]), np.array([1, 2]), np.array([[-1, -5, -10], [-2, -6, -12]]), np.ones((2,3)))
    fig = plot_quarter_wave_overlay(result, table, [], (1, 3))
    np.testing.assert_allclose(fig.axes[0].get_ylim(), [1, 2])
    np.testing.assert_allclose(fig.axes[0].lines[1].get_ydata(), table.quarter_wave_n3_mm)
    plt.close(fig)
