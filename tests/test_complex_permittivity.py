import numpy as np
import pytest

from core.electromagnetic import make_complex


def test_loss_sign_once():
    np.testing.assert_array_equal(make_complex([4, 4], [.2, -.2]), [4-.2j, 4+.2j])


def test_nan_refused():
    with pytest.raises(ValueError):
        make_complex([4], [np.nan])
