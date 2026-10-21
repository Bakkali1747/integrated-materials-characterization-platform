"""故障恢复、按需预览、原网格探索和对照证据的回归测试。"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.models import RLResult
from export.origin_export import save_figure_bundle
from gui.controllers.analysis_controller import AnalysisRequest, analyze_request
from gui.controllers.exploration_controller import thickness_snapshot
from gui.controllers.history_controller import history_index, load_history
from gui.controllers.import_controller import preview_table, validate_template
from gui.controllers.reference_controller import compare_reference, export_reference_comparison
from plotting.style import plt


@pytest.fixture
def completed(tmp_path):
    path=tmp_path/"sample.csv"
    path.write_text("frequency_ghz,eps_real,eps_imag,mu_real,mu_imag\n2,4,.2,1.5,.3\n3,4,.2,1.4,.4\n4,4,.2,1.3,.5\n")
    return analyze_request(AnalysisRequest(path,"sample",output=tmp_path/"runs",thickness_max=1.1,
        thickness_step=.1,dpi=25,full_science=True,quick_preview=True))


@pytest.mark.parametrize("backup",["old_image","old_data"])
def test_rollback_failure_preserves_every_old_byte(tmp_path,monkeypatch,backup):
    import export.origin_export as module
    fig,ax=plt.subplots(); ax.plot([1,2],[3,4]); target=tmp_path/"plot.png"
    save_figure_bundle(fig,target,dpi=20)
    old={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    original=module.replace_path
    def fail(source,dest):
        if Path(source).name in {"image.png",backup}: raise PermissionError("permanent simulated lock")
        return original(source,dest)
    monkeypatch.setattr(module,"replace_path",fail)
    with pytest.raises(RuntimeError,match="RECOVERY.json"):
        save_figure_bundle(fig,target,dpi=20)
    recovery=next(tmp_path.glob(".f-*/RECOVERY.json"))
    available=[p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()]
    assert all(data in available for data in old.values())
    assert json.loads(recovery.read_text(encoding="utf-8"))["image"]==str(target.resolve())
    plt.close(fig)


def test_origin_index_preserves_labels(tmp_path):
    fig,ax=plt.subplots(); ax.plot([1,2],[3,4],label="2.1 mm")
    path=tmp_path/"plot.png"; save_figure_bundle(fig,path,dpi=20)
    index=pd.read_csv(tmp_path/"plot.png.data/index.csv")
    assert index.iloc[0]["label"]=="2.1 mm" and index.iloc[0]["file"]=="01.csv"
    plt.close(fig)


def test_quick_preview_matches_full_analysis(completed,tmp_path):
    request=AnalysisRequest(Path(completed["record"]["raw_file"]),"full",output=tmp_path,
        thickness_max=1.1,thickness_step=.1,dpi=25,full_science=True)
    full=analyze_request(request)
    np.testing.assert_array_equal(full["result"].rl_db,completed["result"].rl_db)
    assert full["summary"]==completed["summary"]
    assert set(full["figures"])==set(completed["figures"])
    assert sum(fig is not None for fig in completed["figures"].values())==4
    assert not list((completed["directory"]/"figures").glob("*.png"))
    assert completed["record"]["figure_output"]=="deferred_until_explicit_export"


def test_thickness_uses_matrix_and_keeps_snapshot(completed,monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError("RL recomputed")
    monkeypatch.setattr("core.rl_calculator.scan_rl",forbidden)
    before=completed["curve"].rl_db.copy()
    snap,details=thickness_snapshot(completed,1)
    np.testing.assert_array_equal(snap["curve"].rl_db[0],completed["result"].rl_db[1])
    assert np.shares_memory(snap["curve"].rl_db,completed["result"].rl_db)
    np.testing.assert_array_equal(before,completed["curve"].rl_db)
    assert details["thickness_mm"]==1.1
    with pytest.raises(ValueError): thickness_snapshot(completed,2)


def test_thickness_separate_bands():
    result=RLResult(np.arange(1.,6.),np.array([2.]),np.array([[-20.,-20.,0.,-20.,-20.]]),np.ones((1,5),complex))
    _,details=thickness_snapshot({"result":result,"record":{"rl_threshold_db":-10}},0)
    assert len(details["standard"]["bands"])==2
    assert details["standard"]["maximum_continuous_bandwidth_ghz"]==1.5


def test_lazy_preview_and_slider(qtbot,completed,monkeypatch):
    from gui.pages.single_sample_page import SingleSamplePage
    page=SingleSamplePage(); qtbot.addWidget(page); page._analyzed(completed); page._set_busy(False)
    page.plot.selector.setCurrentIndex(page.plot.selector.findData("RL_3D"))
    qtbot.waitUntil(lambda:not page.busy,timeout=10000)
    assert page.plot.current_figure() is not None
    page.plot.selector.setCurrentIndex(page.plot.selector.findData("C0"))
    qtbot.waitUntil(lambda:not page.busy,timeout=10000)
    assert page.plot.figures["RL_3D"] is None
    page.thickness_slider.setValue(0)
    qtbot.waitUntil(lambda:not page.busy,timeout=10000)
    assert page.explored["curve"].thickness_mm.tolist()==[1.0]
    assert "1 mm" in page.thickness_summary.text()
    assert "Maximum continuous EAB" in page.thickness_summary.text()
    page.open_plot_data()
    assert "先保存" in page.error.text()


def test_export_explored_curve_and_open_data(qtbot,completed,tmp_path,monkeypatch):
    from gui.pages.single_sample_page import SingleSamplePage
    page=SingleSamplePage(); qtbot.addWidget(page); page._analyzed(completed); page._set_busy(False)
    page.thickness_slider.setValue(0); qtbot.waitUntil(lambda:not page.busy)
    target=tmp_path/"selected.png"
    monkeypatch.setattr("gui.pages.single_sample_page.QFileDialog.getSaveFileName",lambda *a:(str(target),"PNG (*.png)"))
    opened=[]
    monkeypatch.setattr("gui.pages.single_sample_page.QDesktopServices.openUrl",lambda url:opened.append(url.toLocalFile()) or True)
    page.export_dpi=25; page.save_figure(); qtbot.waitUntil(lambda:not page.busy,timeout=10000)
    page.open_plot_data()
    assert opened and Path(opened[0])==target.with_name(target.name+".data")
    values=pd.read_csv(target.with_name(target.name+".data")/"01.csv")
    np.testing.assert_allclose(values.Y,completed["result"].rl_db[0])


def test_slider_initial_position_tracks_curve_thickness(qtbot, completed):
    from gui.pages.single_sample_page import SingleSamplePage
    page = SingleSamplePage(); qtbot.addWidget(page)
    page._analyzed(completed)
    grid = completed["result"].thickness_mm
    # 曲线厚度 2 mm 不在 [1.0, 1.1] 扫描网格中：滑块停在最近点并明确提示。
    assert page.thickness_slider.value() == 1
    assert grid[page.thickness_slider.value()] == pytest.approx(1.1)
    assert "不在扫描网格" in page.thickness_summary.text()
    completed["record"]["configuration"]["curve_thickness_mm"] = 1.1
    page._analyzed(completed)
    assert page.thickness_slider.value() == 1
    assert "不在扫描网格" not in page.thickness_summary.text()


def test_history_verify_uses_current_selection(qtbot, monkeypatch):
    """下拉框选中 B 时，核验必须针对 B，而不是上次加载的 A。"""
    from gui.pages import results_page as module
    page = module.ResultsPage(); qtbot.addWidget(page)
    page.runs.addItem("A", "pathA"); page.runs.addItem("B", "pathB")
    page.completed = {"record_path": "pathA", "directory": Path("A")}
    page.runs.setCurrentIndex(1)
    calls = []
    monkeypatch.setattr(module, "load_history",
                        lambda path, p, c, verify: calls.append((path, verify)) or {})
    page.launch = lambda operation, callback: operation(lambda *a: None, lambda: False)
    page.verify_selected()
    assert calls == [("pathB", True)]


def test_mapping_preview_and_template(qtbot,tmp_path):
    from gui.widgets.mapping_dialog import MappingDialog
    path=tmp_path/"custom.csv"; path.write_text("f,e1,e2,m1,m2\n2,4,.1,1,.2\n")
    table=preview_table(path)
    mapping=dict(zip(["frequency_ghz","eps_real","eps_imag","mu_real","mu_imag"],table.columns))
    template=dict(column_map=mapping,frequency_unit="GHz",imaginary_convention="loss")
    dialog=MappingDialog(table,template); qtbot.addWidget(dialog)
    assert dialog.values()==template
    dialog.fields["eps_real"].setCurrentIndex(dialog.fields["frequency_ghz"].currentIndex())
    with pytest.raises(ValueError): dialog.values()
    with pytest.raises(ValueError): validate_template(dict(template,manufacturer_validated=True))


@pytest.mark.parametrize("extension",["csv","xlsx"])
def test_preview_reads_first_rows_only_for_display(tmp_path,extension):
    path=tmp_path/("table."+extension); data=pd.DataFrame({"x":range(10),"y":range(10)})
    if extension=="csv": data.to_csv(path,index=False)
    else: data.to_excel(path,index=False)
    assert len(preview_table(path))==6


def test_reference_exact_match_and_unmatched(completed):
    result=completed["result"]
    table=pd.DataFrame({"frequency_ghz":[2.,3.,3.1],"thickness_mm":[1.,1.,1.],
                        "rl_db":[result.rl_db[0,0],result.rl_db[0,1]+.2,-10.]})
    report=compare_reference(result,table,.05)
    assert report.status.tolist()==["WITHIN_TOLERANCE","OUTSIDE_TOLERANCE","UNMATCHED"]
    assert report.difference_db.iloc[1]==pytest.approx(-.2)
    assert np.isnan(report.calculated_rl_db.iloc[2])


@pytest.mark.parametrize("problem",["duplicate","nan","missing","negative"])
def test_reference_rejects_invalid(completed,problem):
    table=pd.DataFrame({"frequency_ghz":[2.],"thickness_mm":[1.],"rl_db":[-10.]})
    if problem=="duplicate": table=pd.concat([table,table])
    elif problem=="nan": table.loc[0,"rl_db"]=np.nan
    elif problem=="missing": table=table.drop(columns="rl_db")
    elif problem=="negative": table.loc[0,"frequency_ghz"]=-2
    with pytest.raises(ValueError): compare_reference(completed["result"],table,.05)


def test_reference_report_preserves_validation_and_original(completed,tmp_path):
    original=(completed["directory"]/"analysis_record.json").read_bytes()
    path=tmp_path/"reference.csv"
    pd.DataFrame({"frequency_ghz":[2.],"thickness_mm":[1.],"rl_db":[completed["result"].rl_db[0,0]]}).to_csv(path,index=False)
    target=export_reference_comparison(completed,path,tmp_path/"checks","Synthetic reference; test only")
    record=json.loads((target/"reference_record.json").read_text(encoding="utf-8"))
    assert record["validation_status"]=="pending" and record["counts"]=={"WITHIN_TOLERANCE":1}
    assert (target/"reference_source.csv").read_bytes()==path.read_bytes()
    assert (completed["directory"]/"analysis_record.json").read_bytes()==original


def test_history_fast_load_and_explicit_integrity(tmp_path):
    path=tmp_path/"analysis_record.json"; artifact=tmp_path/"data.csv"; artifact.write_text("changed")
    path.write_text(json.dumps({"sample":"CIP","status":"success","analysis_date":"2026-10-17",
        "configuration":{"thickness_step_mm":.01},"artifacts_sha256":{"data.csv":hashlib.sha256(b"old").hexdigest()}}))
    unchecked=load_history(path,lambda *a:None,lambda:False,verify=False)
    assert unchecked["checks"]==[] and not unchecked["integrity_checked"]
    checked=load_history(path,lambda *a:None,lambda:False)
    assert checked["checks"]==[("data.csv","CHANGED")]
    index=history_index(tmp_path,lambda *a:None,lambda:False)
    assert "CIP" in index[0]["search"] and "0.01" in index[0]["search"]


def test_history_gui_filter(qtbot,tmp_path):
    from gui.pages.results_page import ResultsPage
    page=ResultsPage(); qtbot.addWidget(page)
    entries=[dict(path=tmp_path/str(i),label=name,search=name,status=status)
        for i,(name,status) in enumerate([("CIP 2026-10-17","success"),("Fe3O4 2026-10-16","failed")])]
    page.discovered(entries); assert page.runs.count()==2
    page.search.setText("CIP 2026-10"); assert page.runs.count()==1
    page.status_filter.setCurrentText("failed"); assert page.runs.count()==0
    page.search.clear(); assert page.runs.count()==1
