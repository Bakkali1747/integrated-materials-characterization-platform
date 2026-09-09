import numpy as np
import pytest
from core.eab import absorption_bands, cumulative_frequency_coverage, summarize_bandwidths
from core.models import RLResult


def test_user_continuous_example():
    result = absorption_bands([8.2, 10, 12.4], [-10, -15, -10])
    assert result["maximum_continuous_bandwidth_ghz"] == pytest.approx(4.2)
    assert result["bands"][0]["touches_lower_boundary"]
    assert result["bands"][0]["touches_upper_boundary"]


def test_separated_bands_not_summed():
    result = absorption_bands([3, 4, 5, 6, 8, 10, 11, 13, 14], [-5, -10, -15, -10, -5, -10, -15, -10, -5])
    assert [band["width_ghz"] for band in result["bands"]] == [2, 3]
    assert result["maximum_continuous_bandwidth_ghz"] == 3
    coverage = cumulative_frequency_coverage([result])
    assert coverage["total_coverage_ghz"] == 5
    assert coverage["metric"] == "Cumulative Frequency Coverage"


def test_nonuniform_crossings_and_sample_difference():
    result = absorption_bands([2, 3, 7], [0, -20, 0])
    assert result["bands"][0]["start_ghz"] == 2.5
    assert result["bands"][0]["end_ghz"] == 5
    assert result["maximum_continuous_bandwidth_ghz"] == 2.5
    assert absorption_bands([2, 3, 7], [0, -20, 0], crossing="sample")["maximum_continuous_bandwidth_ghz"] == 0


@pytest.mark.parametrize("curve,width", [([0, 0, 0], 0), ([0, -10, 0], 0), ([-10, -10, -10], 2), ([-15, -15, -15], 2)])
def test_none_touch_plateau_and_full(curve, width):
    assert absorption_bands([2, 3, 4], curve)["maximum_continuous_bandwidth_ghz"] == width


def test_tied_intervals():
    result = absorption_bands([2, 3, 4, 5, 6], [0, -20, 0, -20, 0])
    assert len(result["widest_bands"]) == 2


@pytest.mark.parametrize("curve", [[0, np.nan, -20], [0, np.inf, -20]])
def test_missing_not_bridged(curve):
    with pytest.raises(ValueError):
        absorption_bands([2, 3, 4], curve)


def test_infinity_limit_explicit():
    assert absorption_bands([2, 3], [-np.inf, -np.inf])["maximum_continuous_bandwidth_ghz"] == 1
    with pytest.raises(ValueError, match="无法线性"):
        absorption_bands([2, 3], [0, -np.inf])


def test_best_thickness_and_custom_name():
    result = RLResult(np.array([2, 3, 4]), np.array([1, 2, 3]),
                      np.array([[0, 0, 0], [-20, -20, -20], [-20, -20, -20]]), np.zeros((3, 3)))
    summary = summarize_bandwidths(result)
    assert summary["maximum_bandwidth_ghz"] == 2
    assert [row["thickness_mm"] for row in summary["best_thicknesses"]] == [2, 3]
    assert "EAB" not in summarize_bandwidths(result, -15)["metric"]


def test_coverage_union_across_thickness():
    a = absorption_bands([2, 4, 6], [-20, -20, 0])
    b = absorption_bands([2, 4, 6], [0, -20, -20])
    result = cumulative_frequency_coverage([a, b])
    assert result["intervals_ghz"] == [[2., 6.]]
    assert result["total_coverage_ghz"] == 4


def test_no_absorption_has_no_best_thickness():
    result = RLResult(np.array([2, 3]), np.array([1]), np.array([[0., 0.]]), np.zeros((1, 2)))
    assert summarize_bandwidths(result)["best_thicknesses"] == []
