import numpy as np

from core.impedance import impedance_at_minima
from core.models import RLResult
from core.rl_calculator import normalized_input_impedance, rl_from_impedance
from core.units import C


def test_standard_formula_for_positive_materials():
    f = np.array([2e9, 8e9])
    eps, mu = np.array([4-.2j]*2), np.array([1.5-.3j]*2)
    expected = np.sqrt(mu/eps)*np.tanh(1j*2*np.pi*f*.002/C*np.sqrt(mu*eps))
    np.testing.assert_allclose(normalized_input_impedance(f, eps, mu, [.002])[0], expected)


def test_zero_epsilon_limit():
    z = normalized_input_impedance([2e9], [0], [1], [.001])
    np.testing.assert_allclose(z, [[1j*2*np.pi*2e9*.001/C]])


def test_exact_matching_is_negative_infinity():
    assert np.isneginf(rl_from_impedance([1+0j])[0])


def test_double_negative_branch_is_consistent():
    # ε=μ 时相对阻抗仍为 +1；独立主值平方根可能错误地选择传播方向。
    f = np.array([2e9, 8e9])
    material = np.full(2, -2-.3j)
    expected = np.tanh(1j*2*np.pi*f*.002/C*material)
    np.testing.assert_allclose(normalized_input_impedance(f, material, material, [.002])[0], expected)


def test_unit_modulus_is_not_full_matching():
    assert abs(1j) == 1
    assert rl_from_impedance([1j])[0] == 0
    result = RLResult(np.array([2]), np.array([1]), np.array([[0.]]), np.array([[1j]]))
    row = impedance_at_minima(result)[0]
    assert row["z_abs"] == 1 and row["z_real"] == 0 and row["z_imag"] == 1
    assert row["distance_to_1_plus_0j"] > 1
