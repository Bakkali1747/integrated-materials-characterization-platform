"""分块计算必须与整块计算逐点一致，避免用内存优化换取数值差异。"""
import numpy as np

from core.rl_calculator import normalized_input_impedance, scan_rl
from core.units import ghz_to_hz, mm_to_m


def test_chunked_impedance_matches_single_block():
    frequency = np.linspace(2, 18, 101)
    eps = 4 - .2j + .05 * np.sin(frequency)
    mu = 1.5 - .3j + .02 * np.cos(frequency)
    thickness = np.linspace(1, 5, 37)
    full = normalized_input_impedance(frequency, eps, mu, thickness, chunk_points=None)
    chunked = normalized_input_impedance(frequency, eps, mu, thickness, chunk_points=250)
    assert np.array_equal(full, chunked)


def test_chunked_scan_rl_keeps_shape_and_values():
    frequency = np.linspace(2, 18, 51)
    eps = np.full(51, 4 - .2j)
    mu = np.full(51, 1.5 - .3j)
    thickness = np.linspace(1, 3, 23)
    result = scan_rl(frequency, eps, mu, thickness)
    assert result.rl_db.shape == (23, 51)
    direct = normalized_input_impedance(ghz_to_hz(frequency), eps, mu, mm_to_m(thickness), chunk_points=100)
    assert np.array_equal(result.normalized_impedance, direct)
