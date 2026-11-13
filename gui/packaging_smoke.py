"""冻结版验收入口；走真实 Qt 导入/分析操作，不需要外部 Python。"""

import json
import math
from pathlib import Path

from PySide6.QtCore import QTimer

from application_paths import resource_root, user_data_root


def run_smoke(app, output):
    """输入专用验收目录；记录 UI、解析、图形与追溯结果并返回退出码。"""
    from core.common import WorkspaceRepository
    from gui.controllers.analysis_controller import inspect_file
    from gui.controllers.export_controller import export_figure
    from gui.main_window import MainWindow
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "started", "user_data_root": str(user_data_root())}
    from gui.controllers.settings_controller import SettingsStore, defaults
    smoke_settings = SettingsStore(output / "preferences/gui.json")
    smoke_settings.save(defaults())
    workspace_repository = WorkspaceRepository(output / "workspace")
    window = MainWindow(settings_store=smoke_settings, workspace_repository=workspace_repository)
    window.show()
    source = resource_root() / "sample_data" / "synthetic_constant.csv"
    project = window.workspace.create_project("安装版自检项目", tags=["synthetic", "smoke"])
    sample = window.workspace.create_sample("安装版自检样品", sample_id="SMOKE-001", material_system="Synthetic")
    measurement = window.workspace.add_measurement("electromagnetic", [source])
    report["workspace"] = {
        "project_id": project.project_id,
        "sample_id": sample.sample_id,
        "measurement_id": measurement.measurement_id,
        "source_integrity": workspace_repository.verify_measurement_sources(
            project.project_id, sample.sample_id, measurement.measurement_id
        ),
    }
    page = window.single
    page.parameters.output.setText(str(output / "analysis"))
    page.parameters.fields["thickness_max"].setValue(1.1)
    page.parameters.fields["thickness_step"].setValue(.1)
    window.workspace.start_measurement_analysis()
    phase = "import"
    s_measurement = None
    v_measurement = None
    x_measurement = None

    def save_report():
        (output / "smoke_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def tick():
        nonlocal phase, s_measurement, v_measurement, x_measurement
        if any(p.busy for p in window.task_pages):
            return
        try:
            if phase == "import":
                if not page.start_button.isEnabled():
                    raise RuntimeError(page.error.text())
                page.start_button.click()
                phase = "analyze"
            elif phase == "analyze":
                result = page.completed
                if result is None:
                    raise RuntimeError(page.error.text())
                if len(result["figures"]) != 17:
                    raise RuntimeError("未生成十七类科研图。")
                page.plot.selector.setCurrentIndex(page.plot.selector.findData("RL_multi_thickness"))
                if not (result["directory"] / "RL_multi_thickness.csv").is_file():
                    raise RuntimeError("多厚度 RL 逐点数据未保存")
                report["multi_thickness_mm"] = result["record"]["multi_thickness_rl"]["thickness_mm"]
                report.update(run_directory=str(result["directory"]), git=result["record"]["git"],
                              software_version=result["record"]["software_version"],
                              rl_minima=result["summary"]["global_minima"], figure_count=len(result["figures"]))
                runs = workspace_repository.list_analysis_runs(project.project_id, sample.sample_id,
                                                               measurement.measurement_id)
                if len(runs) != 1 or runs[0].validation_status not in {"PENDING", "WARNING"}:
                    raise RuntimeError("工作区分析运行未自动登记")
                if runs[0].result_refs[0] != str(Path(result["directory"]).resolve()):
                    raise RuntimeError("工作区分析运行缺少结果目录")
                report["workspace_analysis_run"] = {"id": runs[0].analysis_run_id,
                                                    "status": runs[0].validation_status,
                                                    "plot_refs": len(runs[0].plot_refs)}

                def verify(progress, cancelled):
                    for extension in ("png", "tiff", "pdf", "svg"):
                        export_figure(result, "RL_2D", output / f"export.{extension}", progress, cancelled, dpi=40)
                    from export.report import export_report
                    report_files = export_report(result["directory"], output / "analysis_report.docx",
                                                 formats=("docx", "pdf"), dpi=150)
                    if not all(Path(item).is_file() for item in report_files):
                        raise RuntimeError("分析报告验收失败")
                    report["analysis_report"] = "PASS"
                    for extension in ("xlsx", "xls"):
                        path = output / f"synthetic.{extension}"
                        if extension == "xlsx":
                            result["sample"].data.to_excel(path, index=False)
                        else:
                            path.write_bytes((resource_root() / "sample_data/synthetic_legacy.xls").read_bytes())
                        if inspect_file(path, {"imaginary_convention": "loss"})["status"] != "PENDING":
                            raise RuntimeError(f"{extension} parser 失败")
                    return True
                page._launch(verify, lambda ok: report.update(exports_and_excel="PASS"))
                phase = "verify"
            elif phase == "verify":
                if report.get("exports_and_excel") != "PASS" or report.get("analysis_report") != "PASS":
                    raise RuntimeError(page.error.text() or "导出或报告验收失败")
                window.grab().save(str(output / "client.png"))
                path = output / "synthetic.sdat"
                lines = ['<Cluster><Name>SYNTHETIC ONLY</Name></Cluster>']
                lines += ["\t".join(str(x) for x in [2+i*.08, .1, 0, .7, 0, .7, 0, .1, 0]) for i in range(201)]
                path.write_text("\n".join(lines), encoding="utf-8")
                s_measurement = window.workspace.add_measurement("electromagnetic", [path], instrument="VNA")
                spage = window.sparameters
                window.workspace.start_measurement_sparameter_analysis()
                spage.output.setText(str(output))
                spage.start_analysis()
                phase = "sparameters"
            elif phase == "sparameters":
                if not window.sparameters.completed:
                    raise RuntimeError(window.sparameters.error.text())
                report["sparameters"] = window.sparameters.completed["record"]["schema_status"]
                s_runs = workspace_repository.list_analysis_runs(
                    project.project_id, sample.sample_id, s_measurement.measurement_id)
                if len(s_runs) != 1 or s_runs[0].analysis_type != "s_parameters":
                    raise RuntimeError("S 参数运行未自动登记到工作区")
                if s_runs[0].validation_status not in {"PENDING", "WARNING"}:
                    raise RuntimeError("S 参数运行状态不符合待验证规则")
                report["workspace_sparameter_run"] = {"id": s_runs[0].analysis_run_id,
                                                      "status": s_runs[0].validation_status,
                                                      "plot_refs": len(s_runs[0].plot_refs)}
                window.grab().save(str(output / "client-sparameters.png"))
                vsm_path = output / "synthetic_vsm.dat"
                lines = [
                    "ID=SYNTHETIC ONLY  Mass(g)=0.01  Volume(cm^3)=0  Area(mm^2)=0  slope=0  constant=0  "
                    "Unit=CGS  Rate(A/s)=0.500  Room_T(℃)=22.0  PoleGap=Gap2  emuFactor(emu/V)=2.0",
                    "Hci(Oe)=100.0  Mr(emu)=0.1  Ms(emu)=0.2",
                    "Time(s)\tField(Oe)\tTemperature(K)\tAngle(deg)\tMoment(emu)\t"
                    "Magnetization(Mass)(emu/g)\tLockX(V)\tLcokY(V)\tInduction(Gs)",
                ]
                rows = []
                for i in range(101):
                    h = 3000 - 60 * i
                    m = 0.01 * 20 * math.tanh((h + 100) / 120)
                    rows.append("\t".join(["12:00:00.000", f"{h:.6E}", "NaN", "NaN", f"{m:.6E}",
                                           f"{m / 0.01:.6E}", "0", "0", "Inf"]))
                for i in range(1, 101):
                    h = -3000 + 60 * i
                    m = 0.01 * 20 * math.tanh((h - 100) / 120)
                    rows.append("\t".join(["12:00:01.000", f"{h:.6E}", "NaN", "NaN", f"{m:.6E}",
                                           f"{m / 0.01:.6E}", "0", "0", "Inf"]))
                vsm_path.write_text("\n".join(lines + rows), encoding="utf-8")
                v_measurement = window.workspace.add_measurement("vsm", [vsm_path], instrument="VSM")
                window.workspace.start_measurement_vsm_analysis()
                window.vsm.output.setText(str(output / "vsm-analysis"))
                window.vsm.start_analysis()
                phase = "vsm"
            elif phase == "vsm":
                if not window.vsm.completed:
                    raise RuntimeError(window.vsm.error.text() or "VSM 分析失败")
                metrics = window.vsm.completed["metrics"]
                if metrics.get("Hc_oe") is None or metrics.get("Mr") is None:
                    raise RuntimeError("VSM 指标未计算")
                v_runs = workspace_repository.list_analysis_runs(
                    project.project_id, sample.sample_id, v_measurement.measurement_id)
                if len(v_runs) != 1 or v_runs[0].analysis_type != "vsm_hysteresis":
                    raise RuntimeError("VSM 运行未自动登记到工作区")
                if v_runs[0].validation_status not in {"PENDING", "WARNING", "NOT_COMPUTABLE"}:
                    raise RuntimeError("VSM 运行状态不符合待验证规则")
                report["workspace_vsm_run"] = {"id": v_runs[0].analysis_run_id,
                                               "status": v_runs[0].validation_status,
                                               "plot_refs": len(v_runs[0].plot_refs),
                                               "Hc_oe": metrics.get("Hc_oe"),
                                               "Mr": metrics.get("Mr")}
                from export.vsm_report import export_vsm_report
                report["vsm_reports"] = [str(item) for item in export_vsm_report(
                    window.vsm.completed["directory"], output / "vsm_report", dpi=120)]
                window.grab().save(str(output / "client-vsm.png"))
                xrd_path = output / "synthetic_xrd.txt"
                xrd_lines = [";RAW4.00", "[RawHeader]", "Date=08/03/2026", "Time=20:23:19", "",
                             "[HardwareConfiguration]", "Alpha1=1.5406", "Alpha2=1.54439",
                             "AlphaAverage=1.5418", "", "[RangeHeader]", "Start=10.0",
                             "Increment=0.02", "ActuallyUsedLambda=1.5418",
                             "NumberOfMeasuredData=4001", "", "[VarInfo]", "Type=SAMPLEID",
                             "Value=SYNTHETIC XRD", "", "[Data]", "Angle, PSD,"]
                for i in range(4001):
                    angle = 10.0 + i * 0.02
                    intensity = (100.0 + 0.5 * angle
                                 + 500.0 * math.exp(-((angle - 20.0) / 0.08) ** 2)
                                 + 300.0 * math.exp(-((angle - 30.0) / 0.10) ** 2)
                                 + 200.0 * math.exp(-((angle - 40.0) / 0.12) ** 2))
                    xrd_lines.append(f"{angle:.4f}, {intensity:.6f},")
                xrd_path.write_text("\n".join(xrd_lines), encoding="utf-8")
                x_measurement = window.workspace.add_measurement("xrd", [xrd_path], instrument="XRD")
                window.workspace.start_measurement_xrd_analysis()
                window.xrd.output.setText(str(output / "xrd-analysis"))
                window.xrd.start_analysis()
                phase = "xrd"
            elif phase == "xrd":
                if not window.xrd.completed:
                    raise RuntimeError(window.xrd.error.text() or "XRD 分析失败")
                peaks = window.xrd.completed["metrics"]["peaks"]
                if not peaks:
                    raise RuntimeError("XRD 未检测到峰")
                x_runs = workspace_repository.list_analysis_runs(
                    project.project_id, sample.sample_id, x_measurement.measurement_id)
                if len(x_runs) != 1 or x_runs[0].analysis_type != "xrd_peaks":
                    raise RuntimeError("XRD 运行未自动登记到工作区")
                if x_runs[0].validation_status not in {"PENDING", "WARNING", "NOT_COMPUTABLE"}:
                    raise RuntimeError("XRD 运行状态不符合待验证规则")
                report["workspace_xrd_run"] = {"id": x_runs[0].analysis_run_id,
                                               "status": x_runs[0].validation_status,
                                               "plot_refs": len(x_runs[0].plot_refs),
                                               "peak_count": len(peaks)}
                from export.xrd_report import export_xrd_report
                report["xrd_reports"] = [str(item) for item in export_xrd_report(
                    window.xrd.completed["directory"], output / "xrd_report", dpi=120)]
                window.grab().save(str(output / "client-xrd.png"))
                compare = window.comparison
                compare.add_source(output / "synthetic.xlsx", "synthetic_copy")
                compare.parameters.output.setText(str(output))
                compare.parameters.fields["thickness_max"].setValue(1.1)
                compare.parameters.fields["thickness_step"].setValue(.1)
                window.navigation.setCurrentRow(6)
                compare.start_comparison()
                phase = "comparison"
            elif phase == "comparison":
                result = window.comparison.completed
                if not result or result["record"]["success_count"] != 2 or len(result["figures"]) != 10:
                    raise RuntimeError(window.comparison.error.text() or "比较验收失败")
                report["comparison_metric_count"] = len(result["figures"])
                window.grab().save(str(output / "client-comparison.png"))
                batch_source = output / "batch-input"
                batch_source.mkdir(exist_ok=True)
                (batch_source / "synthetic.csv").write_bytes(source.read_bytes())
                (batch_source / "synthetic.sdat").write_bytes((output / "synthetic.sdat").read_bytes())
                (batch_source / "broken.csv").write_text("bad\n1")
                bpage = window.batch
                bpage.parameters.output.setText(str(output / "batch-output"))
                bpage.parameters.fields["thickness_max"].setValue(1.1)
                bpage.parameters.fields["thickness_step"].setValue(.1)
                window.navigation.setCurrentRow(7)
                bpage.scan(batch_source)
                phase = "batch-scan"
            elif phase == "batch-scan":
                if len(window.batch.items) != 3:
                    raise RuntimeError("批量目录扫描失败")
                window.batch.start()
                phase = "batch-run"
            elif phase == "batch-run":
                result = window.batch.completed
                if not result or result["record"]["success_count"] != 2 or result["record"]["failed_count"] != 1:
                    raise RuntimeError(window.batch.error.text() or "批量失败隔离验收失败")
                report["batch"] = {k:result["record"][k] for k in ("status", "success_count", "failed_count")}
                window.grab().save(str(output / "client-batch.png"))
                window.navigation.setCurrentRow(8)
                window.history.discovered([result["directory"] / "batch_record.json"])
                window.history.load_selected()
                phase = "history"
            elif phase == "history":
                result = window.history.completed
                if not result or result.get("integrity_checked"):
                    raise RuntimeError("历史快速读取未按预期保持未核验状态")
                window.history.verify_selected()
                phase = "history-verified"
            elif phase == "history-verified":
                result = window.history.completed
                if not result or not result["checks"] or any(s != "PASS" for _,s in result["checks"]):
                    raise RuntimeError("历史读取与完整性核对失败")
                if window.history.image.pixmap() is None or window.history.image.pixmap().isNull():
                    raise RuntimeError("历史图片未显示")
                report["history_integrity"] = "PASS"
                report["quality_control"] = "PASS" if "Quality Control" in page.summary.toPlainText() else "FAIL"
                if report["quality_control"] != "PASS":
                    raise RuntimeError("Quality Control 未展示")
                window.grab().save(str(output / "client-history.png"))
                window.navigation.setCurrentRow(9)
                analysis_dpi = page.completed["record"]["configuration"]["figure_dpi"]
                window.settings.dpi.setValue(120)
                window.settings.format.setCurrentText("svg")
                window.settings.fields["thickness_step"].setValue(.02)
                window.settings.save_button.click()
                saved, warning = smoke_settings.load()
                if warning or saved["dpi"] != 120 or saved["figure_format"] != "svg":
                    raise RuntimeError("设置保存验收失败")
                reopened = MainWindow(settings_store=smoke_settings, workspace_repository=workspace_repository)
                if reopened.single.parameters.figure_dpi != 120 or reopened.sparameters.figure_format != "svg":
                    raise RuntimeError("设置重启恢复失败")
                if len(workspace_repository.list_projects()) != 1 or len(workspace_repository.list_samples()) != 1:
                    raise RuntimeError("项目与样品工作区重启恢复失败")
                reopened.close(); reopened.deleteLater()
                report["settings_persistence"] = "PASS"
                report["existing_snapshot_unchanged"] = page.completed["record"]["configuration"]["figure_dpi"] == analysis_dpi
                window.grab().save(str(output / "client-settings.png"))
                from gui.controllers.export_controller import export_all_builders
                from gui.controllers.science_figures import make_figure
                from plotting.style import PlotStyle
                result = page.completed
                builders = {key:lambda k=key:make_figure(result,k,PlotStyle(dpi=120)) for key in result["figures"]}
                page._launch(lambda p,c:export_all_builders(builders,result["directory"],output/"all-figures","svg",120,p,c),
                             lambda directory:report.update(all_figures_directory=str(directory)))
                phase = "all-exports"
            elif phase == "all-exports":
                directory = Path(report.get("all_figures_directory", "missing"))
                record = json.loads((directory / "export_record.json").read_text(encoding="utf-8"))
                if record["status"] != "success" or len(record["completed"]) != 17:
                    raise RuntimeError("全部图片导出验收失败")
                report["all_figure_exports"] = len(record["completed"])
                images = [p for p in output.rglob("*")
                          if p.suffix.lower() in {".png", ".tiff", ".pdf", ".svg"}
                          and not p.name.startswith("client")
                          and p.stem not in {"analysis_report", "vsm_report", "xrd_report"}]
                for image_path in images:
                    data_folder = image_path.with_name(image_path.name + ".data")
                    manifest = json.loads((data_folder / "metadata.json").read_text(encoding="utf-8"))
                    if not manifest["datasets"] or not all((data_folder / item["file"]).is_file() for item in manifest["datasets"]):
                        raise RuntimeError(f"图片配套数据缺失：{image_path}")
                report["origin_data_image_count"] = len(images)
                def optimization_check(progress,cancelled):
                    import numpy as np
                    import pandas as pd

                    from gui.controllers.analysis_controller import AnalysisRequest, analyze_request
                    from gui.controllers.exploration_controller import thickness_snapshot
                    from gui.controllers.import_controller import preview_table
                    from gui.controllers.reference_controller import export_reference_comparison
                    quick=analyze_request(AnalysisRequest(source,"quick",output=output/"quick",thickness_max=1.1,
                        thickness_step=.1,dpi=120,full_science=True,quick_preview=True),progress,cancelled)
                    np.testing.assert_array_equal(quick["result"].rl_db,page.completed["result"].rl_db)
                    if any((quick["directory"]/"figures").iterdir()): raise RuntimeError("快速预览意外导出高清图片")
                    snapshot,_=thickness_snapshot(quick,1)
                    reference=output/"reference.csv"
                    pd.DataFrame({"frequency_ghz":snapshot["curve"].frequency_ghz,"thickness_mm":1.1,
                        "rl_db":snapshot["curve"].rl_db[0]}).to_csv(reference,index=False)
                    target=export_reference_comparison(quick,reference,output/"reference-checks","Synthetic smoke reference only")
                    record=json.loads((target/"reference_record.json").read_text(encoding="utf-8"))
                    if record["validation_status"]!="pending": raise RuntimeError("对照意外改变验证状态")
                    if len(preview_table(source))!=6: raise RuntimeError("导入预览失败")
                    return quick
                page._launch(optimization_check,page._analyzed)
                phase="optimization-preview"
            elif phase == "optimization-preview":
                if not page.completed["record"]["configuration"].get("quick_preview"):
                    raise RuntimeError(page.error.text() or "快速预览验收失败")
                page.plot.selector.setCurrentIndex(page.plot.selector.findData("RL_3D"))
                phase="optimization-thickness"
            elif phase == "optimization-thickness":
                if page.plot.current_figure() is None: raise RuntimeError("按需三维预览失败")
                grid = page.completed["result"].thickness_mm
                target_index = 0 if page.thickness_slider.value() != 0 else min(1, len(grid) - 1)
                report["slider_expected_mm"] = float(grid[target_index])
                page.thickness_slider.setValue(target_index)
                phase="optimization-finished"
            elif phase == "optimization-finished":
                expected = report.get("slider_expected_mm")
                if page.explored is None or page.explored["curve"].thickness_mm[0] != expected:
                    raise RuntimeError("厚度滑块验收失败")
                report["optimizations"]="PASS: quick preview, lazy 3D, grid thickness, reference evidence, import preview"
                report["status"] = "success"
                save_report()
                window.close()
                app.quit()
        except Exception as error:
            report.update(status="failed", error=str(error))
            save_report()
            app.exit(1)

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(200)
    return app.exec()
