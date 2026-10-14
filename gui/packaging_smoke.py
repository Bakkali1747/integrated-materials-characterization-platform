"""冻结版验收入口；走真实 Qt 导入/分析操作，不需要外部 Python。"""

import json
from pathlib import Path
from PySide6.QtCore import QTimer
from application_paths import resource_root, user_data_root


def run_smoke(app, output):
    """输入专用验收目录；记录 UI、解析、图形与追溯结果并返回退出码。"""
    from gui.main_window import MainWindow
    from gui.controllers.analysis_controller import inspect_file
    from gui.controllers.export_controller import export_figure
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "started", "user_data_root": str(user_data_root())}
    from gui.controllers.settings_controller import SettingsStore, defaults
    smoke_settings = SettingsStore(output / "preferences/gui.json")
    smoke_settings.save(defaults())
    window = MainWindow(settings_store=smoke_settings)
    window.show()
    window.navigation.setCurrentRow(1)
    page = window.single
    source = resource_root() / "sample_data" / "synthetic_constant.csv"
    page.parameters.output.setText(str(output / "analysis"))
    page.parameters.fields["thickness_max"].setValue(1.1)
    page.parameters.fields["thickness_step"].setValue(.1)
    page.import_paths([source])
    phase = "import"

    def save_report():
        (output / "smoke_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def tick():
        nonlocal phase
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

                def verify(progress, cancelled):
                    for extension in ("png", "tiff", "pdf", "svg"):
                        export_figure(result, "RL_2D", output / f"export.{extension}", progress, cancelled, dpi=40)
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
                if report.get("exports_and_excel") != "PASS":
                    raise RuntimeError(page.error.text())
                window.grab().save(str(output / "client.png"))
                path = output / "synthetic.sdat"
                lines = ['<Cluster><Name>SYNTHETIC ONLY</Name></Cluster>']
                lines += ["\t".join(str(x) for x in [2+i*.08, .1, 0, .7, 0, .7, 0, .1, 0]) for i in range(201)]
                path.write_text("\n".join(lines), encoding="utf-8")
                spage = window.sparameters
                spage.file.setText(str(path)); spage.name.setText("synthetic_sparameters"); spage.output.setText(str(output))
                window.navigation.setCurrentRow(2)
                spage.start_analysis()
                phase = "sparameters"
            elif phase == "sparameters":
                if not window.sparameters.completed:
                    raise RuntimeError(window.sparameters.error.text())
                report["sparameters"] = window.sparameters.completed["record"]["schema_status"]
                window.grab().save(str(output / "client-sparameters.png"))
                compare = window.comparison
                compare.add_source(output / "synthetic.xlsx", "synthetic_copy")
                compare.parameters.output.setText(str(output))
                compare.parameters.fields["thickness_max"].setValue(1.1)
                compare.parameters.fields["thickness_step"].setValue(.1)
                window.navigation.setCurrentRow(3)
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
                window.navigation.setCurrentRow(4)
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
                window.navigation.setCurrentRow(5)
                window.history.discovered([result["directory"] / "batch_record.json"])
                window.history.load_selected()
                phase = "history"
            elif phase == "history":
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
                window.navigation.setCurrentRow(6)
                window.settings.dpi.setValue(120)
                window.settings.format.setCurrentText("svg")
                window.settings.fields["thickness_step"].setValue(.02)
                window.settings.save_button.click()
                saved, warning = smoke_settings.load()
                if warning or saved["dpi"] != 120 or saved["figure_format"] != "svg":
                    raise RuntimeError("设置保存验收失败")
                reopened = MainWindow(settings_store=smoke_settings)
                if reopened.single.parameters.figure_dpi != 120 or reopened.sparameters.figure_format != "svg":
                    raise RuntimeError("设置重启恢复失败")
                reopened.close(); reopened.deleteLater()
                report["settings_persistence"] = "PASS"
                report["existing_snapshot_unchanged"] = page.completed["record"]["configuration"]["figure_dpi"] == 600
                window.grab().save(str(output / "client-settings.png"))
                from gui.controllers.export_controller import export_all_builders
                from gui.controllers.science_figures import make_figure
                from plotting.style import PlotStyle
                result = page.completed
                builders = {key:lambda k=key:make_figure(result,k,PlotStyle(dpi=120)) for key in result["figures"]}
                page._launch(lambda p,c:export_all_builders(builders,result["directory"],output/"all-figures","svg",120,p,c),
                             lambda directory:report.update(all_figures_directory=str(directory)))
                phase = "all-exports"
            else:
                directory = Path(report.get("all_figures_directory", "missing"))
                record = json.loads((directory / "export_record.json").read_text(encoding="utf-8"))
                if record["status"] != "success" or len(record["completed"]) != 17:
                    raise RuntimeError("全部图片导出验收失败")
                report["all_figure_exports"] = len(record["completed"])
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
