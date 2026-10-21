"""配套 CSV 必须使用图片数据，且不能改图或留下不匹配的输出。"""
import json
import os
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.rl_calculator import scan_rl
from export.origin_export import save_figure_bundle
from plotting.comparison_plot import plot_comparison
from plotting.impedance_plot import plot_impedance_2d, plot_impedance_curve, plot_rl_impedance
from plotting.mechanism_plot import plot_quarter_wave, plot_quarter_wave_overlay
from plotting.rl_plot import plot_rl_2d, plot_rl_3d, plot_rl_multi_thickness
from plotting.style import plt


@pytest.fixture
def matrix():
    return scan_rl([2.,2.08,2.16],[4-.2j]*3,[1.5-.3j]*3,[1.,2.,3.])


def load_bundle(path):
    directory=path.with_name(path.name+".data")
    metadata=json.loads((directory/"metadata.json").read_text(encoding="utf-8"))
    return [(entry,pd.read_csv(directory/entry["file"],float_precision="round_trip")) for entry in metadata["datasets"]]


@pytest.mark.parametrize("extension",["png","tiff","pdf","svg"])
def test_separate_csv_and_unchanged_artists(tmp_path,extension):
    fig,ax=plt.subplots(); line,=ax.plot([2.,3.],[.12345678901234567,8.],label="sample A")
    ax.set(xlabel="Frequency (GHz)",ylabel="RL (dB)",title="Keep title")
    before=(line.get_color(),line.get_linestyle(),ax.get_title(),len(fig.axes),len(ax.lines),list(fig.texts))
    path=tmp_path/f"figure.{extension}"
    save_figure_bundle(fig,path,dpi=30)
    entries=load_bundle(path)
    assert entries[0][0]["label"]=="sample A" and entries[0][0]["x_label"]=="Frequency (GHz)"
    np.testing.assert_array_equal(entries[0][1].Y,line.get_ydata())
    assert before==(line.get_color(),line.get_linestyle(),ax.get_title(),len(fig.axes),len(ax.lines),list(fig.texts))
    assert path.is_file() and (tmp_path/(path.name+".data")/"01.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    plt.close(fig)


@pytest.mark.parametrize("kind",["RL2D","RL3D","impedance","dual"])
def test_full_grid_not_contour_vertices(matrix,tmp_path,kind):
    factories={"RL2D":lambda:plot_rl_2d(matrix)[0],"RL3D":lambda:plot_rl_3d(matrix)[0],
               "impedance":lambda:plot_impedance_2d(matrix)[0],"dual":lambda:plot_rl_impedance(matrix)}
    fig=factories[kind]();path=tmp_path/"map.png";save_figure_bundle(fig,path,dpi=25)
    grids=[frame for info,frame in load_bundle(path) if info["kind"]=="grid"]
    assert len(grids)==(2 if kind=="dual" else 1)
    np.testing.assert_array_equal(grids[0].X,np.tile(matrix.frequency_ghz,3))
    np.testing.assert_array_equal(grids[0].Y,np.repeat(matrix.thickness_mm,3))
    expected=abs(matrix.normalized_impedance) if kind=="impedance" else matrix.rl_db
    np.testing.assert_array_equal(grids[0].Z,expected.reshape(-1))
    plt.close(fig)


def test_independent_sample_grids_preserved(tmp_path):
    fig=plot_comparison([dict(name="A",x=[2,3],y=[1,2]),dict(name="B",x=[2.1,3.3,4],y=[3,4,5])],"eps_real")
    path=tmp_path/"compare.png";save_figure_bundle(fig,path,dpi=25)
    entries=load_bundle(path)
    assert [len(table) for _,table in entries]==[2,3]
    assert entries[1][1].X.tolist()==[2.1,3.3,4]
    plt.close(fig)


def test_multithickness_and_reference(matrix,tmp_path):
    fig=plot_rl_multi_thickness(matrix,[0,2]);path=tmp_path/"multi.png";save_figure_bundle(fig,path,dpi=25)
    entries=load_bundle(path)
    assert [entry[0]["label"] for entry in entries[:2]]==["1 mm","3 mm"]
    np.testing.assert_array_equal(entries[1][1].Y,matrix.rl_db[2])
    assert entries[-1][0]["kind"]=="horizontal_reference"
    assert entries[-1][1].Y.tolist()==[-10,-10]
    plt.close(fig)


@pytest.mark.parametrize("overlay",[False,True])
def test_quarterwave_scatter_preserved(matrix,tmp_path,overlay):
    table=pd.DataFrame(dict(frequency_ghz=matrix.frequency_ghz,quarter_wave_n1_mm=[3,2,1]))
    comparison=[dict(frequency_ghz=2.08,actual_thickness_mm=2.)]
    fig=plot_quarter_wave_overlay(matrix,table,comparison) if overlay else plot_quarter_wave(table,comparison)
    path=tmp_path/"quarter.png";save_figure_bundle(fig,path,dpi=25)
    scatter=[data for info,data in load_bundle(path) if info["kind"]=="scatter"]
    assert len(scatter)==1 and scatter[0].X.tolist()==[2.08] and scatter[0].Y.tolist()==[2.]
    plt.close(fig)


def test_nan_and_infinity_not_removed(tmp_path):
    fig,ax=plt.subplots();ax.plot([1,2,3],[np.nan,-np.inf,5])
    path=tmp_path/"limits.png";save_figure_bundle(fig,path,dpi=25)
    values=load_bundle(path)[0][1].Y.to_numpy()
    assert len(values)==3 and np.isnan(values[0]) and values[1]==-np.inf
    plt.close(fig)


def test_impedance_reference_band(matrix,tmp_path):
    fig=plot_impedance_curve(matrix);path=tmp_path/"z.png";save_figure_bundle(fig,path,dpi=25)
    entries=load_bundle(path)
    bands=[table for info,table in entries if info["kind"]=="reference_band"]
    assert len(bands)==1
    np.testing.assert_allclose(bands[0].iloc[0],[.9,1.1])
    plt.close(fig)


def test_cancel_preserves_previous_pair(tmp_path):
    fig,ax=plt.subplots();ax.plot([1,2],[3,4]);path=tmp_path/"plot.png"
    save_figure_bundle(fig,path,dpi=25)
    before={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    calls=[]
    def cancel():
        calls.append(1);return len(calls)>2
    with pytest.raises(InterruptedError):
        save_figure_bundle(fig,path,dpi=25,cancelled=cancel)
    after={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert before==after
    plt.close(fig)


def test_failed_pair_commit_rolls_back(tmp_path,monkeypatch):
    import export.origin_export as module
    fig,ax=plt.subplots();ax.plot([1,2],[3,4]);path=tmp_path/"plot.png"
    save_figure_bundle(fig,path,dpi=25)
    before={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    original=module.os.replace
    def fail(source,target):
        if Path(source).name=="image.png":
            raise PermissionError("simulated image commit failure")
        return original(source,target)
    monkeypatch.setattr(module.os,"replace",fail)
    with pytest.raises(PermissionError):
        save_figure_bundle(fig,path,dpi=25)
    assert before=={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    plt.close(fig)


def test_unrelated_directory_preserved(tmp_path):
    fig,ax=plt.subplots();ax.plot([1,2],[3,4]);path=tmp_path/"plot.png"
    directory=tmp_path/"plot.png.data";directory.mkdir();(directory/"keep.txt").write_text("keep")
    with pytest.raises(ValueError):
        save_figure_bundle(fig,path,dpi=25)
    assert not path.exists() and (directory/"keep.txt").read_text()=="keep"
    plt.close(fig)


def test_transient_windows_lock_retried(tmp_path,monkeypatch):
    import export.origin_export as module
    source=tmp_path/"source";source.write_text("data")
    target=tmp_path/"target";original=module.os.replace;calls=[]
    def locked(a,b):
        calls.append(1)
        if len(calls)<3:
            error=PermissionError("busy");error.winerror=32;raise error
        original(a,b)
    monkeypatch.setattr(module.os,"replace",locked)
    monkeypatch.setattr(module.time,"sleep",lambda _:None)
    module.replace_path(source,target)
    assert len(calls)==3 and target.read_text()=="data"


def test_permanent_windows_denial_has_bounded_retries(monkeypatch):
    import export.origin_export as module
    calls=[]
    def denied(a,b):
        calls.append(1);error=PermissionError("denied");error.winerror=5;raise error
    monkeypatch.setattr(module.os,"replace",denied)
    monkeypatch.setattr(module.time,"sleep",lambda _:None)
    with pytest.raises(PermissionError):
        module.replace_path("source","target")
    assert len(calls)==6


def test_identical_grids_share_storage(tmp_path, matrix):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    save_figure_bundle(plot_rl_2d(matrix)[0], first, dpi=25)
    save_figure_bundle(plot_rl_2d(matrix)[0], second, dpi=25)
    left = first.with_name(first.name + ".data") / "01.csv"
    right = second.with_name(second.name + ".data") / "01.csv"
    assert os.stat(left).st_ino == os.stat(right).st_ino
    shutil.rmtree(left.parent)
    values = pd.read_csv(right)
    assert len(values) == 3 * 3


def test_multi_thickness_reference_uses_requested_threshold(matrix):
    fig = plot_rl_multi_thickness(matrix, [0, 2], threshold=-15)
    reference = [line for line in fig.axes[0].lines if line.get_label() == "-15 dB"]
    assert reference and reference[0].get_ydata()[0] == -15
    plt.close(fig)


def test_bundle_records_provenance_and_default_unknown(tmp_path):
    fig, ax = plt.subplots(); ax.plot([1, 2], [1, 2], label="curve")
    provenance = {"software_version": "9.9.9", "run_id": "run-1", "sample": "S",
                  "raw_sha256": "a" * 64, "validation_status": "pending_x",
                  "configuration_sha256": "b" * 64, "dpi": 30, "created_at": "2026-01-01T00:00:00+08:00"}
    path = tmp_path / "p.png"
    save_figure_bundle(fig, path, dpi=30, provenance=provenance)
    directory = path.with_name(path.name + ".data")
    manifest = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    assert manifest["provenance"]["run_id"] == "run-1"
    assert manifest["provenance"]["validation_status"] == "pending_x"
    assert json.loads((directory / "provenance.json").read_text(encoding="utf-8"))["raw_sha256"] == "a" * 64
    index = pd.read_csv(directory / "index.csv")
    assert list(index.columns[:2]) == ["run_id", "validation_status"]
    assert index.iloc[0]["run_id"] == "run-1"
    plt.close(fig)

    fig, ax = plt.subplots(); ax.plot([1, 2], [1, 2])
    anonymous = tmp_path / "q.png"
    save_figure_bundle(fig, anonymous, dpi=30)
    manifest = json.loads((anonymous.with_name(anonymous.name + ".data") / "metadata.json").read_text(encoding="utf-8"))
    assert manifest["provenance"]["validation_status"] == "unknown"
    plt.close(fig)


def test_companion_file_conflict_has_clear_error(tmp_path):
    fig, ax = plt.subplots(); ax.plot([1, 2], [1, 2])
    target = tmp_path / "conflict.png"
    target.with_name(target.name + ".data").write_text("occupied", encoding="utf-8")
    with pytest.raises(ValueError, match="同名文件"):
        save_figure_bundle(fig, target, dpi=30)
    plt.close(fig)
