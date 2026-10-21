import numpy as np
import pytest

from core.rl_calculator import calculate_rl, minimum_points, scan_rl
from core.units import C


def test_lossless_backed_layer_reflects_all():
    f = np.linspace(2e9, 18e9, 21)
    np.testing.assert_allclose(calculate_rl(f, f*0+4, f*0+2, [.001, .003]), 0, atol=1e-12)


def test_matched_lossy_layer_analytic_solution():
    # ε=μ=a-jb 时 zc=1，Γ=-exp(-2jk0nd)，RL=-40*k0*b*d/ln(10)。
    f = np.array([2e9, 8e9, 18e9])
    d = np.array([.001, .003])
    material = np.full(3, 2-.4j)
    expected = -40 * (2*np.pi*f[None, :]/C) * .4*d[:, None]/np.log(10)
    np.testing.assert_allclose(calculate_rl(f, material, material, d), expected, atol=1e-12)


def test_zero_thickness():
    np.testing.assert_allclose(calculate_rl([2e9], [4-.2j], [1-.1j], [0]), [[0]])


def test_minimum_indices_and_shape():
    result = scan_rl([2, 8, 18], [2-.4j]*3, [2-.4j]*3, [1, 3])
    assert result.rl_db.shape == (2, 3)
    points = minimum_points(result)
    assert len(points) == 1
    assert points[0]["frequency_ghz"] == 18 and points[0]["thickness_mm"] == 3


def test_nan_refused():
    with pytest.raises(ValueError):
        calculate_rl([2e9], [complex(np.nan)], [1], [0.001])
