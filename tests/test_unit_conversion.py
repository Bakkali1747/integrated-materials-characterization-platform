import numpy as np
import pytest

from core.units import ghz_to_hz, mm_to_m, thickness_grid


def test_units():
    np.testing.assert_allclose(ghz_to_hz([2, 18]), [2e9, 18e9])
    np.testing.assert_allclose(mm_to_m([1, 5]), [.001, .005])


def test_decimal_endpoint():
    grid = thickness_grid()
    assert len(grid) == 401
    assert grid[0] == 1 and grid[-1] == 5
    np.testing.assert_allclose(thickness_grid(1, 1.1, .03), [1, 1.03, 1.06, 1.09])


@pytest.mark.parametrize("values", [(0, 5, .1), (2, 1, .1), (1, 5, 0), (1, 5, float('nan'))])
def test_invalid_thickness(values):
    with pytest.raises(ValueError):
        thickness_grid(*values)
