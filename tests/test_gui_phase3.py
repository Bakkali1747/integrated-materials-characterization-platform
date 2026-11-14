"""Phase 3 编排、取消、只读历史与 Qt 信号验收。"""
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from gui.controllers import batch_controller as batch
from gui.controllers.analysis_controller import AnalysisRequest, Cancelled
from gui.controllers.history_controller import contained, discover_history, load_history
from gui.controllers.quality_controller import quality_rows
from gui.pages.batch_page import BatchPage
from gui.pages.results_page import ResultsPage


@pytest.fixture
def analysis_request(tmp_path):
    path = tmp_path / "material.csv"
    path.write_text("frequency_ghz,eps_real,eps_imag,mu_real,mu_imag\n2,4,.2,1.5,.3\n3,4,.2,1.4,.4\n4,4,.2,1.3,.5\n")
    return AnalysisRequest(path, "material", output=tmp_path/"output", thickness_max=1.1, thickness_step=.1, dpi=25)


@pytest.fixture
def mixed(analysis_request):
    path = analysis_request.path.with_suffix(".sdat")
    lines = ["<Cluster><Name>SYNTHETIC</Name></Cluster>"] + ["\t".join(str(v) for v in [2+i*.08,.1,0,.7,0,.7,0,.1,0]) for i in range(201)]
    path.write_text("\n".join(lines))
    bad = analysis_request.path.parent / "broken.csv"; bad.write_text("bad\n1")
    return [analysis_request, replace(analysis_request,path=path), replace(analysis_request,path=bad,name="broken")]


def test_scan_direct_only(analysis_request):
    nested = analysis_request.path.parent/"nested"; nested.mkdir(); (nested/"ignored.csv").write_text("bad")
    items = batch.scan_folder(analysis_request.path.parent, analysis_request.parser_options, lambda *a:None, lambda:False)
    assert len(items)==1 and items[0]["points"]==3


def test_scan_failure_isolation(mixed):
    items = batch.scan_folder(mixed[0].path.parent, {"imaginary_convention":"loss"}, lambda *a:None, lambda:False)
    assert len(items)==3 and sum(i["status"]=="FAIL" for i in items)==1


def test_batch_reuses_completed_run(analysis_request):
    first = batch.run_batch_requests([analysis_request], analysis_request.output, lambda *a: None, lambda: False,
                                     reuse=True)
    second = batch.run_batch_requests([analysis_request], analysis_request.output, lambda *a: None, lambda: False,
                                      reuse=True)
    assert second["record"]["reused_count"] == 1
    member = second["record"]["members"][0]
    assert member["reused_from"] == first["record"]["members"][0]["run_directory"]
    assert member["status"] == "success"


def test_scan_cancel(analysis_request):
    with pytest.raises(Cancelled):
        batch.scan_folder(analysis_request.path.parent, {}, lambda *a:None, lambda:True)


def test_mixed_batch_and_history(mixed):
    events=[]; progress=[]
    result=batch.run_batch_requests(mixed,mixed[0].output,lambda n,t:progress.append(n),lambda:False, events.append)
    r=result["record"]
    assert r["status"]=="partial_failure" and r["success_count"]==2 and r["failed_count"]==1
    assert len(events)==6 and progress[-1]==100
    assert r["members"][1]["kind"]=="Measured S Parameters"
    assert r["members"][1]["validation"]=="candidate_high_confidence"
    assert (result["directory"]/"materials_summary.xlsx").exists()
    history=load_history(result["directory"]/"batch_record.json",lambda *a:None,lambda:False)
    assert all(s=="PASS" for _,s in history["checks"])
    assert history["record"]["status"]=="partial_failure"
    assert "sources.csv" in history["summaries"]
    progress_log = (result["directory"]/"members.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(progress_log) == len(r["members"]) == 3
    assert {json.loads(line)["index"] for line in progress_log} == {0, 1, 2}


def test_cancel_before_start(analysis_request):
    result=batch.run_batch_requests([analysis_request],analysis_request.output,lambda *a:None,lambda:True)
    assert result["record"]["status"]=="cancelled"
    assert result["record"]["not_started_count"]==1


def test_cancel_preserves_finished(analysis_request):
    stop=[]
    result=batch.run_batch_requests([analysis_request,replace(analysis_request,name="next")],analysis_request.output,lambda *a:None,lambda:bool(stop),lambda m:stop.append(True) if m["status"]=="success" else None)
    assert result["record"]["success_count"]==1 and result["record"]["not_started_count"]==1
    child=Path(result["record"]["members"][0]["run_directory"])
    assert json.loads((child/"analysis_record.json").read_text(encoding="utf-8"))["status"]=="success"


def test_cancel_during_member(analysis_request):
    stop=[]
    result=batch.run_batch_requests([analysis_request],analysis_request.output,lambda n,t:stop.append(True) if n>=50 else None,lambda:bool(stop))
    assert result["record"]["cancelled_count"]==1
    assert list(result["directory"].rglob("RL_matrix.csv"))


def test_empty_batch(analysis_request):
    with pytest.raises(ValueError):
        batch.run_batch_requests([],analysis_request.output,lambda *a:None,lambda:False)


@pytest.mark.parametrize("state", ["success","failed","cancelled","partial_failure"])
def test_history_preserves_state(tmp_path,state):
    path=tmp_path/"analysis_record.json"; path.write_text(json.dumps({"status":state}))
    before=path.read_bytes()
    result=load_history(path,lambda *a:None,lambda:False)
    assert result["record"]["status"]==state and path.read_bytes()==before
    assert all(s!="PASS" for _,s,_ in quality_rows(result["record"]))


@pytest.mark.parametrize("name", ["../outside.png", "C:/outside.png"])
def test_history_path_escape(tmp_path,name):
    with pytest.raises(ValueError):
        contained(tmp_path,name)


@pytest.mark.parametrize("changed", [True,False])
def test_history_missing_or_changed(tmp_path,changed):
    path=tmp_path/"analysis_record.json"
    path.write_text(json.dumps({"artifacts_sha256":{"plot.png":hashlib.sha256(b"before").hexdigest()}}))
    if changed:
        (tmp_path/"plot.png").write_bytes(b"after")
    result=load_history(path,lambda *a:None,lambda:False)
    assert result["checks"]==[("plot.png","CHANGED" if changed else "MISSING")]


def test_history_discovery(tmp_path):
    (tmp_path/"analysis_record.json").write_text("{}")
    (tmp_path/"other.json").write_text("{}")
    assert len(discover_history(tmp_path,lambda *a:None,lambda:False))==1


def test_qc_evidence_and_pending():
    rows=quality_rows({"source":{"parser":"csv-v1"},"frequency_points":3,"schema_status":"candidate_high_confidence"})
    assert all(s=="PASS" for _,s,_ in rows[:4])
    assert all(s=="PENDING" for _,s,_ in rows[4:])


def test_qc_physical_warnings():
    rows=quality_rows({"quality_checks":{"negative_absorption_count":1,"energy_violation_count":0,"reciprocity":{"violation_count":2}}})
    assert ("negative_absorption_count","WARNING","1") in rows
    assert ("energy_violation_count","PASS","0") in rows
    assert rows[-1][1]=="WARNING"


def test_batch_grouping(qtbot,mixed):
    page=BatchPage(); qtbot.addWidget(page)
    items=batch.scan_folder(mixed[0].path.parent,{},lambda *a:None,lambda:False)
    page.scanned(items)
    assert page.table.topLevelItemCount()==2 and len(page.rows)==3


def test_batch_thread_signals(qtbot,analysis_request,monkeypatch):
    from PySide6.QtCore import QThread
    page=BatchPage(); qtbot.addWidget(page)
    page.scanned([batch.inspect_file(analysis_request.path,{})]); page.parameters.output.setText(str(analysis_request.output))
    threads=[]
    def fake(requests,output,progress,cancelled,member,reuse=False):
        threads.append(QThread.currentThread()); progress(100,"done")
        member(dict(index=0,status="success",sample="material"))
        return dict(directory=output,record=dict(status="success",success_count=1,failed_count=0,cancelled_count=0,not_started_count=0))
    monkeypatch.setattr("gui.pages.batch_page.run_batch_requests",fake)
    page.start()
    qtbot.waitUntil(lambda:not page.busy)
    assert threads[0]!=page.thread() and page.progress.value()==100
    assert page.rows[0].text(3)=="success"


def test_history_page_load(qtbot,tmp_path):
    page=ResultsPage(); qtbot.addWidget(page)
    path=tmp_path/"analysis_record.json"; path.write_text('{"status":"cancelled"}')
    page.discovered([path]); page.load_selected()
    qtbot.waitUntil(lambda:not page.busy)
    assert "cancelled" in page.metadata.toPlainText()
    assert page.completed["directory"]==tmp_path


def test_history_bad_json(qtbot,tmp_path):
    page=ResultsPage(); qtbot.addWidget(page)
    path=tmp_path/"analysis_record.json"; path.write_text("bad")
    page.discovered([path]); page.load_selected()
    qtbot.waitUntil(lambda:not page.busy)
    assert page.error.text() and "Traceback" not in page.error.text()


def test_phase3_navigation(qtbot):
    from gui.main_window import MainWindow
    window=MainWindow(); qtbot.addWidget(window)
    window.show_page("em.batch"); assert window.stack.currentWidget() is window.batch
    window.show_page("history"); assert window.stack.currentWidget() is window.history
    assert len(window.task_pages)==13
