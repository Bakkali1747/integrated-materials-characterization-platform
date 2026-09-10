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
    window = MainWindow()
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
        if page.busy:
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
                if len(result["figures"]) != 4:
                    raise RuntimeError("未生成四类基础图。")
                page.plot.selector.setCurrentIndex(3)
                report.update(run_directory=str(result["directory"]), git=result["record"]["git"],
                              software_version=result["record"]["software_version"],
                              rl_minima=result["summary"]["global_minima"], figure_count=4)

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
            else:
                if report.get("exports_and_excel") != "PASS":
                    raise RuntimeError(page.error.text())
                window.grab().save(str(output / "client.png"))
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
