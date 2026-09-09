import numpy as np
import pytest
from core.mechanism import (attenuation_constant, loss_tangent, eddy_current_c0,
                            quarter_wave_thickness, mechanism_parameters, quarter_wave_minima_comparison)
from core.models import SampleData
from core.rl_calculator import scan_rl
from core.units import C


def test_attenuation_analytic_matched_medium():
    f = np.array([2e9, 10e9, 18e9])
    material = np.full(3, 2-.4j)
    np.testing.assert_allclose(attenuation_constant(f, material, material), 2*np.pi*f*.4/C, rtol=1e-13)


def test_low_loss_attenuation_avoids_cancellation():
    f = np.array([10e9])
    material = np.array([2-1e-12j])
    np.testing.assert_allclose(attenuation_constant(f, material, material), 2*np.pi*f*1e-12/C, rtol=1e-13)


def test_attenuation_matches_propagation_constant():
    f = np.array([2e9, 7e9, 18e9])
    eps = np.array([4-.3j, 3-.5j, 2-1j])
    mu = np.array([2-.1j, 1.5-.3j, 1-.4j])
    alpha = -2*np.pi*f/C*np.sqrt(eps*mu).imag
    np.testing.assert_allclose(attenuation_constant(f, eps, mu), alpha)


def test_lossless_and_evanescent_limit():
    np.testing.assert_array_equal(attenuation_constant([1e9], [4], [1]), [0])
    np.testing.assert_allclose(attenuation_constant([1e9], [-4], [1]), [2*np.pi*1e9*2/C])


def test_tangent_sign_and_singular():
    result = loss_tangent([4, -4, 0], [.2, .2, .2])
    np.testing.assert_allclose(result[:2], [.05, -.05])
    assert np.isnan(result[2])


def test_c0_si_units():
    np.testing.assert_allclose(eddy_current_c0([2e9], [2], [.4]), [.4/(4*2e9)])
    assert np.isnan(eddy_current_c0([2e9], [0], [.4])[0])


def test_quarter_wave_vacuum_orders_and_units():
    f = np.array([3e9, 6e9])
    n1 = quarter_wave_thickness(f, [1, 1], [1, 1], 1)
    np.testing.assert_allclose(n1, C/(4*f))
    np.testing.assert_allclose(quarter_wave_thickness(f, [1, 1], [1, 1], 3), 3*n1)


@pytest.mark.parametrize("order", [0, 2, -1, 1.5, True])
def test_invalid_order(order):
    with pytest.raises(ValueError):
        quarter_wave_thickness([1e9], [4], [1], order)


def test_nan_input_refused():
    with pytest.raises(ValueError):
        attenuation_constant([1e9], [complex(np.nan)], [1])


def test_derived_zero_denominators_warn_and_preserve_raw(frame):
    frame.loc[0, "mu_real"] = 0
    frame.loc[1, ["eps_real", "eps_imag"]] = 0
    original = frame.copy(deep=True)
    sample = SampleData("synthetic", frame, {})
    table, warnings = mechanism_parameters(sample, (1, 3))
    assert np.isnan(table.c0_seconds.iloc[0])
    assert np.isnan(table.quarter_wave_n1_mm.iloc[1])
    assert len(warnings) >= 3
    assert frame.equals(original)


def test_quarter_comparison_uses_actual_rl_frequency(frame):
    sample = SampleData("synthetic", frame, {})
    table, _ = mechanism_parameters(sample, (1, 3))
    result = scan_rl(frame.frequency_ghz, [2-.4j]*3, [2-.4j]*3, [1, 2])
    comparison = quarter_wave_minima_comparison(result, table, (1, 3))
    assert len(comparison) == 2
    assert comparison[0]["frequency_ghz"] == 4
    assert comparison[0]["quarter_wave_n3_mm"] == table.quarter_wave_n3_mm.iloc[-1]
