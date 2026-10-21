"""屏蔽效能与 Smith 图的数值/绘图回归。"""
import numpy as np
import pytest

from core.sparameters import analyze_sparameters
from plotting.sparameter_plot import plot_shielding_effectiveness, plot_smith
from plotting.style import plt


def test_shielding_effectiveness_from_known_power():
    frequency = np.array([2., 3.])
    s11 = np.full(2, np.sqrt(.5) + 0j)
    s21 = np.full(2, np.sqrt(.25) + 0j)
    table, qc = analyze_sparameters(frequency, {"S11": s11, "S21": s21, "S12": s21, "S22": s11})
    assert table["SE_R_db"].iloc[0] == pytest.approx(3.0102999566, abs=1e-9)
    assert table["SE_A_db"].iloc[0] == pytest.approx(3.0102999566, abs=1e-9)
    assert table["SE_T_db"].iloc[0] == pytest.approx(6.0205999133, abs=1e-9)
    assert qc["se_undefined_count"] == 0


def test_shielding_undefined_for_r_at_least_one():
    frequency = np.array([2., 3.])
    s11 = np.ones(2, dtype=complex)
    s21 = np.full(2, .1 + 0j)
    table, qc = analyze_sparameters(frequency, {"S11": s11, "S21": s21, "S12": s21, "S22": s11})
    assert np.isnan(table["SE_R_db"]).all() and np.isnan(table["SE_A_db"]).all()
    assert np.isfinite(table["SE_T_db"]).all()
    assert qc["se_undefined_count"] == 2


def test_smith_and_se_figures_use_table_data():
    frequency = np.array([2., 3., 4.])
    s11 = np.array([.1+.1j, .2+.2j, .3+.3j])
    s22 = np.array([.05+.05j, .1+.1j, .15+.15j])
    s21 = np.full(3, .5 + 0j)
    table, _ = analyze_sparameters(frequency, {"S11": s11, "S21": s21, "S12": s21, "S22": s22})
    smith = plot_smith(table)
    se = plot_shielding_effectiveness(table)
    assert len(smith.axes[0].lines) >= 2 and len(smith.axes[0].patches) > 0
    assert len(se.axes[0].lines) == 3
    plt.close(smith)
    plt.close(se)
