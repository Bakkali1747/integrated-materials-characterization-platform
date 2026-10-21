"""设置持久化、参数快照、导出和可缩放历史图片测试。"""
import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from gui.controllers.analysis_controller import Cancelled
from gui.controllers.export_controller import export_all_builders
from gui.controllers.settings_controller import SettingsStore, defaults, validate_settings
from gui.main_window import MainWindow
from gui.widgets.image_view import ImageView
from plotting.style import plt


@pytest.fixture
def store(tmp_path):
    return SettingsStore(tmp_path/"preferences/gui.json")


def test_defaults_do_not_create_file(store):
    values, warning = store.load()
    assert values["interpolation"]=="OFF" and values["dpi"]==300 and not warning
    assert not store.path.exists()


def test_settings_round_trip(store,tmp_path):
    values=defaults(); values.update(thickness_step=.02,dpi=300,figure_format="svg",output=str(tmp_path))
    assert store.save(values)==store.load()[0]
    assert store.load()[1]==""


@pytest.mark.parametrize("field,value",[("dpi",0),("dpi",True),("dpi",12.5),("dpi",1201),("interpolation","ON"),("figure_format","exe"),("frequency_unit","guess"),("version",2),("version",True),("thickness_min",9),("threshold",float("nan")),("thickness_step",0),("output","relative/path"),("output","")])
def test_invalid_preferences_rejected(field,value):
    values=defaults(); values[field]=value
    with pytest.raises(ValueError):
        validate_settings(values)


def test_unknown_settings_not_silently_accepted():
    with pytest.raises(ValueError):
        validate_settings({"manufacturer_validated":True})


def test_corrupt_settings_preserved(store):
    store.path.parent.mkdir(); store.path.write_text("invalid")
    values,warning=store.load()
    assert warning and values==defaults() and store.path.read_text(encoding="utf-8")=="invalid"


def test_atomic_save_failure_keeps_old_settings(store,monkeypatch):
    store.save(defaults()); before=store.path.read_bytes()
    def fail(*args):
        raise PermissionError("read only")
    monkeypatch.setattr("gui.controllers.settings_controller.os.replace",fail)
    with pytest.raises(PermissionError):
        store.save(dict(defaults(),dpi=300))
    assert store.path.read_bytes()==before
    assert len(list(store.path.parent.iterdir()))==1


def test_output_cannot_be_file(store,tmp_path):
    target=tmp_path/"file"; target.write_text("data")
    with pytest.raises(ValueError):
        store.save(dict(defaults(),output=str(target)))


def test_settings_gui_restart_and_no_analysis(qtbot,store,tmp_path):
    window=MainWindow(settings_store=store); qtbot.addWidget(window)
    window.settings.dpi.setValue(300); window.settings.format.setCurrentText("svg")
    window.settings.fields["thickness_step"].setValue(.02); window.settings.output.setText(str(tmp_path))
    window.settings.save_button.click()
    assert store.path.exists() and not any(p.busy for p in window.task_pages)
    assert window.single.completed is None
    other=MainWindow(settings_store=store); qtbot.addWidget(other)
    for page in (other.single,other.comparison,other.batch):
        assert page.parameters.figure_dpi==300 and page.parameters.fields["thickness_step"].value()==.02
        assert page.figure_format=="svg"
    assert other.sparameters.output.text()==str(tmp_path)
    assert other.sparameters.export_dpi==600


def test_setting_apply_does_not_change_existing_snapshot(qtbot,store):
    window=MainWindow(settings_store=store); qtbot.addWidget(window)
    snapshot={"record":{"configuration":{"figure_dpi":600}}}
    window.single.completed=snapshot
    window.save_settings(dict(defaults(),dpi=300))
    assert snapshot["record"]["configuration"]["figure_dpi"]==600


def test_settings_do_not_override_memp_units(qtbot,store,tmp_path):
    window=MainWindow(settings_store=store); qtbot.addWidget(window)
    window.save_settings(dict(defaults(),frequency_unit="MHz"))
    options=window.single.parameters.parser_options(tmp_path/"sample.memp")
    assert "frequency_unit" not in options and options["convention_confirmed"] is False


def test_failed_save_not_applied(qtbot,store,monkeypatch):
    window=MainWindow(settings_store=store); qtbot.addWidget(window)
    def fail(values):
        raise PermissionError("no write")
    monkeypatch.setattr(store,"save",fail)
    window.save_settings(dict(defaults(),dpi=300))
    assert window.single.parameters.figure_dpi==300 and "保存失败" in window.settings.message.text()


def test_running_task_rejects_settings(qtbot,store):
    window=MainWindow(settings_store=store); qtbot.addWidget(window)
    window.single.worker=object()
    try:
        window.update_task_lock()
        assert not window.settings.isEnabled()
        window.save_settings(dict(defaults(),dpi=300))
        assert not store.path.exists()
    finally:
        window.single.worker=None; window.update_task_lock()


def test_history_image_fits_resize(qtbot):
    image=ImageView(); qtbot.addWidget(image); image.resize(200,100); image.show()
    pixmap=QPixmap(900,650); pixmap.fill(Qt.GlobalColor.white); image.set_image(pixmap)
    assert image.pixmap().width()<=200 and image.pixmap().height()<=100
    image.resize(400,300); qtbot.wait(20)
    assert image.pixmap().width()<=400 and image.pixmap().height()<=300
    image.clear(); assert image.original.isNull()


def make_test_figure():
    fig,ax=plt.subplots(); ax.plot([1,2],[3,4]); return fig


@pytest.mark.parametrize("extension",["png","tiff","pdf","svg"])
def test_export_all_formats(tmp_path,extension):
    source=tmp_path/"source"; source.mkdir(); (source/"analysis_record.json").write_text('{}', encoding="utf-8")
    directory=export_all_builders({"synthetic":make_test_figure},source,tmp_path/"exports",extension,72,lambda *a:None,lambda:False)
    record=json.loads((directory/"export_record.json").read_text(encoding="utf-8"))
    assert record["status"]=="success" and record["dpi"]==72
    assert (directory/f"synthetic.{extension}").stat().st_size>100
    assert "analysis_record.json" in record["source_records_sha256"]


def test_export_all_cancel_preserves_completed(tmp_path):
    stop=[]
    with pytest.raises(Cancelled):
        export_all_builders({"first":make_test_figure,"second":make_test_figure},tmp_path/"source",tmp_path/"exports","svg",72,lambda *a:stop.append(True),lambda:bool(stop))
    record_path=next((tmp_path/"exports").rglob("export_record.json"))
    record=json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"]=="cancelled" and record["completed"]==["first.svg"]
    assert not list(record_path.parent.glob("tmp*"))


def test_export_all_rejects_source_overwrite(tmp_path):
    with pytest.raises(ValueError):
        export_all_builders({"plot":make_test_figure},tmp_path,tmp_path/"child","png",72,lambda *a:None,lambda:False)
