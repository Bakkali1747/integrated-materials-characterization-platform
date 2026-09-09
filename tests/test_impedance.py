import numpy as np
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
