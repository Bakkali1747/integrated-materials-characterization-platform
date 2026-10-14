"""多厚度叠图必须逐行使用原 RL 矩阵，不能插值或修改旧结果。"""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from core.rl_calculator import scan_rl
from plotting.rl_plot import representative_thickness_indices, plot_rl_multi_thickness
from plotting.style import PlotStyle, plt
from gui.controllers.analysis_controller import AnalysisRequest, analyze_request
from gui.controllers.export_controller import export_figure


@pytest.fixture
def matrix():
    return scan_rl([2., 2.08, 2.16], [4-.2j]*3, [1.5-.3j]*3, np.linspace(1,5,401))


def test_automatic_includes_optima_and_bounds(matrix):
    indices=representative_thickness_indices(matrix,[matrix.thickness_mm[123],matrix.thickness_mm[245]])
    assert {0,400,123,245} <= set(indices)
    assert indices==sorted(set(indices)) and len(indices)<=9


@pytest.mark.parametrize("count",[1,2,7])
def test_small_grids_show_every_thickness(matrix,count):
    matrix.thickness_mm=matrix.thickness_mm[:count]
    assert representative_thickness_indices(matrix)==list(range(count))


def test_no_nearest_thickness_substitution(matrix):
    with pytest.raises(ValueError):
        representative_thickness_indices(matrix,[1.234567])


def test_curves_exactly_match_matrix(matrix):
    before=matrix.rl_db.copy()
    indices=representative_thickness_indices(matrix,[2.5])
    fig=plot_rl_multi_thickness(matrix,indices,PlotStyle(dpi=30))
    for line,i in zip(fig.axes[0].lines,indices):
        np.testing.assert_array_equal(line.get_xdata(),matrix.frequency_ghz)
        np.testing.assert_array_equal(line.get_ydata(),matrix.rl_db[i])
    assert list(fig.axes[0].lines[-1].get_ydata())==[-10,-10]
    assert fig._suptitle is None
    np.testing.assert_array_equal(matrix.rl_db,before)
    plt.close(fig)


def test_infinite_rl_not_clipped(matrix):
    matrix.rl_db[0,0]=-np.inf
    with pytest.raises(ValueError):
        plot_rl_multi_thickness(matrix,[0])


@pytest.fixture(scope="module")
def analyzed(tmp_path_factory):
    root=tmp_path_factory.mktemp("multi_thickness")
    return analyze_request(AnalysisRequest(Path("sample_data/synthetic_constant.csv"),"synthetic",output=root,
        full_science=True,dpi=30,frequency_min=3,frequency_max=5))


def test_gui_analysis_outputs_automatic_figure_and_data(analyzed):
    assert "RL_multi_thickness" in analyzed["figures"]
    record=analyzed["record"]["multi_thickness_rl"]
    table=pd.read_csv(analyzed["directory"]/"RL_multi_thickness.csv")
    assert record["frequency_interpolation"]=="OFF"
    for i in record["row_indices"]:
        rows=table[table.thickness_mm==analyzed["result"].thickness_mm[i]]
        np.testing.assert_allclose(rows.rl_db,analyzed["result"].rl_db[i],atol=1e-13,rtol=1e-13)
        np.testing.assert_array_equal(rows.frequency_ghz,analyzed["result"].frequency_ghz)
    assert (analyzed["directory"]/"figures/RL_multi_thickness.png").is_file()


@pytest.mark.parametrize("extension",["png","tiff","pdf","svg"])
def test_existing_export_supports_new_view(analyzed,tmp_path,extension):
    target=tmp_path/f"multi.{extension}"
    export_figure(analyzed,"RL_multi_thickness",target,lambda *a:None,lambda:False,dpi=30)
    assert target.stat().st_size>100
