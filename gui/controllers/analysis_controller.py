"""Phase 1 流程适配；数值、频带和绘图全部调用已有 API。"""

import json
import logging
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

from application_paths import user_data_root
from core.analysis_service import AnalysisConfig, execute, load_completed_run
from core.fixture import fixture_for_path
from core.reuse import index_completed_runs, run_key, sha256_file
from core.sparameter_parser import read_sparameters
from export.origin_export import save_figure_bundle
from export.provenance import artifact_hashes, figure_provenance, json_safe, write_record
from plotting.em_parameters import plot_parameters
from plotting.rl_plot import plot_rl_2d, plot_rl_curve
from plotting.style import plt, style_for

ROOT = user_data_root()
SUPPORTED = {".csv", ".xlsx", ".xls", ".memp", ".sdat"}
PENDING = "pending_imaginary_convention_and_commercial_reference"
FILENAME_HINTS = re.compile(r"^(?P<sample>\d+(?:\.\d+)?)_(?P<fmin>\d+(?:\.\d+)?)_(?P<fmax>\d+(?:\.\d+)?)_(?P<points>\d+)_(?P<temp>\d+)")


def filename_hints(path):
    """解析实验室命名：编号_起始_终止_点数_温度；0.2 是样品编号，不是厚度。"""
    match = FILENAME_HINTS.match(Path(path).stem)
    if not match:
        return {}
    return {"sample_id": match["sample"],
            "frequency_min_ghz": float(match["fmin"]),
            "frequency_max_ghz": float(match["fmax"]),
            "points": int(match["points"]),
            "temperature_c": int(match["temp"])}


class Cancelled(Exception):
    """协作式取消；只在完整步骤之间停止，不删除已保存数据。"""


@dataclass
class AnalysisRequest:
    """输入展示单位参数；parser_options 显式保存文件解释方式。"""
    path: Path
    name: str
    output: Path = ROOT / "output"
    thickness_min: float = 1.0
    thickness_max: float = 5.0
    thickness_step: float = 0.01
    curve_thickness: float = 2.0
    threshold: float = -10.0
    frequency_min: float | None = None
    frequency_max: float | None = None
    dpi: int = 600
    full_science: bool = False
    quick_preview: bool = False
    eab_crossing: str = "linear"
    quarter_wave_orders: tuple = (1,)
    impedance_tolerance: float = .1
    figure_preset: str = "screen"
    reuse: bool = False
    parser_options: dict = field(default_factory=lambda: {"imaginary_convention": "loss"})
    source_hints: dict = field(default_factory=dict)


def request_with_fixture_thickness(request):
    """批量/比较时为每个 .memp 读取同目录 .sdat 的 D；缺失则保留用户参数。"""
    if Path(request.path).suffix.lower() != ".memp":
        return request
    fixture = fixture_for_path(request.path)
    thickness = fixture.get("thickness_mm")
    if thickness is None:
        return request
    hints = dict(request.source_hints)
    hints["fixture"] = fixture
    return replace(request, curve_thickness=float(thickness), source_hints=hints)


def _reuse_configuration(request):
    return {"requested_frequency_range_ghz": [request.frequency_min, request.frequency_max],
            "requested_thickness_range_mm": [request.thickness_min, request.thickness_max],
            "thickness_step_mm": request.thickness_step, "curve_thickness_mm": request.curve_thickness,
            "rl_threshold_db": request.threshold, "eab_threshold_crossing": request.eab_crossing,
            "parser_options": dict(request.parser_options),
            "quarter_wave_orders": list(request.quarter_wave_orders),
            "impedance_tolerance": request.impedance_tolerance}


def reused_result(run):
    """把已完成运行的数值对象包装成 GUI 结果；图按需重新生成。"""
    directory, record, d = run.directory, run.record, run.thickness_mm
    keys = ["permittivity", "permeability", "RL_curve", "RL_2D"]
    if len(d) > 1:
        keys.append("RL_3D")
    science = {}
    if (directory / "loss_parameters.csv").is_file():
        keys += ["loss_tangent", "tan_delta_eps", "tan_delta_mu", "attenuation", "C0", "Cole_Cole",
                 "impedance_curve", "impedance", "RL_impedance"]
        science["science_table"] = pd.read_csv(directory / "loss_parameters.csv")
    if (directory / "quarter_wave_comparison.csv").is_file():
        keys += ["quarter_wave", "RL_quarter_wave"]
        science["quarter_comparison"] = pd.read_csv(directory / "quarter_wave_comparison.csv").to_dict("records")
    if record.get("multi_thickness_rl"):
        keys.append("RL_multi_thickness")
    return {"directory": directory, "sample": run.sample, "result": run.result, "curve": run.curve,
            "summary": run.summary, "record": record, "figures": {key: None for key in keys}, **science}


def inspect_file(path, parser_options):
    """输入文件与显式解析配置；返回导入表信息，不进行 RL 计算。"""
    path = Path(path).resolve()
    info = {"path": path, "sample": path.stem, "format": path.suffix.lower(),
            "size": None, "status": "FAIL", "points": None, "frequency": None}
    try:
        info["size"] = path.stat().st_size
        if path.suffix.lower() not in SUPPORTED:
            raise ValueError("不支持此格式；请选择 .memp / .sdat / .csv / .xlsx / .xls。")
        if path.suffix.lower() == ".sdat":
            data = read_sparameters(path)
            frequency = data.frequency_ghz
            info.update(status="candidate_high_confidence", parser="candidate SParameterMapping")
        else:
            from core.parser import read_sample
            data = read_sample(path, **parser_options)
            frequency = data.data.frequency_ghz.to_numpy()
            info.update(status="PENDING", parser=data.metadata["parser"], sample=data.name)
        info.update(points=len(frequency), frequency=(float(frequency[0]), float(frequency[-1])))
        info["filename_hints"] = filename_hints(path)
        info["fixture"] = fixture_for_path(path)
    except Exception as error:
        import logging
        logging.getLogger("microwave.gui").exception("导入失败：%s", path)
        info["error"] = str(error)
    return info


def analyze_request(request, progress=lambda percent, text: None, cancelled=lambda: False):
    """输入不可变任务快照；返回已有模型、摘要、Figure 与追溯目录。

    核心数值管线由 core.analysis_service 统一执行；本函数只负责 GUI 图组、
    可选快速预览和成功状态。取消在阶段边界生效，不中断一次数值调用。
    """
    r = request
    figures = {}
    run = None

    def checkpoint(percent, message):
        if cancelled():
            raise Cancelled("已取消；已写入结果保留，当前运行不标记为成功。")
        progress(percent, message)

    config = AnalysisConfig(
        path=Path(r.path), name=r.name, output=Path(r.output),
        thickness_min=r.thickness_min, thickness_max=r.thickness_max, thickness_step=r.thickness_step,
        curve_thickness=r.curve_thickness, threshold=r.threshold,
        frequency_min=r.frequency_min, frequency_max=r.frequency_max, eab_crossing=r.eab_crossing,
        parser_options=r.parser_options, entry_point="gui_phase1", name_for_parser=r.name,
        extra_configuration={"quarter_wave_orders": list(r.quarter_wave_orders),
                             "impedance_tolerance": r.impedance_tolerance,
                             "figure_preset": r.figure_preset,
                             "source_hints": dict(r.source_hints),
                             "figure_dpi": r.dpi, "full_science": r.full_science,
                             "quick_preview": r.quick_preview})
    try:
        if not np.isfinite([r.dpi]).all() or r.dpi <= 0:
            raise ValueError("DPI 必须 > 0。")
        if not r.quarter_wave_orders or any(
                isinstance(n, bool) or not isinstance(n, (int, np.integer)) or n < 1 or n % 2 != 1
                for n in r.quarter_wave_orders):
            raise ValueError("四分之一波长阶数必须为非空正奇数整数列表。")
        if len(set(r.quarter_wave_orders)) != len(r.quarter_wave_orders):
            raise ValueError("四分之一波长阶数不能重复。")
        if not np.isfinite(r.impedance_tolerance) or not 0 < r.impedance_tolerance < 1:
            raise ValueError("阻抗模长显示容差必须在 0 与 1 之间。")
        if r.reuse:
            try:
                cached = index_completed_runs(r.output).get(
                    run_key(r.name, sha256_file(r.path), _reuse_configuration(r)))
                if cached is not None:
                    progress(10, "复用已完成运行")
                    reused = load_completed_run(cached)
                    progress(100, "复用完成，未重新计算")
                    return reused_result(reused)
            except (OSError, ValueError, KeyError):
                logging.getLogger("microwave.gui").exception("复用运行不可用，改为重新计算")
        run = execute(config, progress=checkpoint, cancelled=cancelled, cancel_exception=Cancelled)
        sample, result, curve = run.sample, run.result, run.curve
        directory, record, summary = run.directory, run.record, run.summary
        standard, minima = run.standard_eab, record["global_minima"]
        d, f = run.thickness_mm, run.frequencies
        provenance = figure_provenance(record, dpi=r.dpi)
        style = style_for(r.figure_preset, r.dpi)
        factories = [("permittivity", lambda: plot_parameters(sample, "permittivity", style)),
                     ("permeability", lambda: plot_parameters(sample, "permeability", style))]
        if np.isfinite(result.rl_db).all() and np.isfinite(curve.rl_db).all():
            factories += [("RL_curve", lambda: plot_rl_curve(curve, style=style, threshold=r.threshold)),
                          ("RL_2D", lambda: plot_rl_2d(result, style)[0])]
        else:
            sample.warnings.append("RL 存在无限极限，保留原值；当前绘图不截断，跳过 RL 图。")
        folder = directory / "figures"
        folder.mkdir()
        for index, (key, factory) in enumerate(factories):
            checkpoint(55 + index * 5, f"绘图与保存：{key}")
            fig = factory()
            figures[key] = fig
            if not r.quick_preview:
                save_figure_bundle(fig, folder / f"{key}.png", dpi=r.dpi, provenance=provenance)
            plt.close(fig)  # 解除 pyplot 管理；Figure 仍交由 Qt Canvas 持有。
        science = {}
        if r.full_science:
            from export.phase2_export import export_phase2
            from gui.controllers.science_figures import make_figure

            def save_science(fig, filename):
                # 取消检查放在持有 Figure 后，异常路径也可统一释放。
                key = Path(filename).stem
                figures[key] = fig
                checkpoint(min(96, 70 + len(figures)), f"科研图：{key}")
                save_figure_bundle(fig, folder / filename, dpi=r.dpi, provenance=provenance)
                plt.close(fig)

            record["phase2"] = export_phase2(sample, result, curve, directory, save_science, style,
                                               r.quarter_wave_orders, r.impedance_tolerance,
                                               render_figures=not r.quick_preview)
            if r.quick_preview:
                for key in ("loss_tangent", "attenuation", "C0", "Cole_Cole", "quarter_wave",
                            "impedance_curve", "impedance"):
                    figures[key] = None
                if np.isfinite(result.rl_db).all():
                    figures.update(RL_impedance=None, RL_quarter_wave=None)
            summary["phase2"] = record["phase2"]
            science = {"science_table": pd.read_csv(directory / "loss_parameters.csv"),
                       "quarter_comparison": pd.read_csv(directory / "quarter_wave_comparison.csv").to_dict("records")}
            context = {"sample": sample, "result": result, "curve": curve, "record": record, **science}
            extra = ["tan_delta_eps", "tan_delta_mu"]
            if np.isfinite(result.rl_db).all():
                from plotting.rl_plot import representative_thickness_indices
                important = [minima[0]["thickness_mm"]]
                if standard["best_thicknesses"]:
                    important.append(standard["best_thicknesses"][0]["thickness_mm"])
                indices = representative_thickness_indices(result, important)
                record["multi_thickness_rl"] = {
                    "selection": "up_to_7_uniform_grid_rows_plus_first_global_minimum_and_first_maximum_eab",
                    "row_indices": indices, "thickness_mm": [float(d[i]) for i in indices],
                    "source": "existing_RL_matrix", "frequency_interpolation": "OFF",
                    "reference_threshold_db": -10,
                    "note": "自动选取代表厚度；并列最优的全部明细仍在原摘要中。"}
                pd.concat([pd.DataFrame({"frequency_ghz": f, "thickness_mm": d[i], "rl_db": result.rl_db[i]})
                           for i in indices], ignore_index=True).to_csv(directory / "RL_multi_thickness.csv", index=False)
                extra.append("RL_multi_thickness")
            if len(d) > 1 and np.isfinite(result.rl_db).all():
                extra.append("RL_3D")
            for key in extra:
                if r.quick_preview:
                    figures[key] = None
                else:
                    save_science(make_figure(context, key, style), key + ".png")
            (directory / "summary.json").write_text(
                json.dumps(json_safe(summary), ensure_ascii=False, indent=2), encoding="utf-8")
        checkpoint(98, "完成来源追踪")
        record["figure_output"] = "deferred_until_explicit_export" if r.quick_preview else "saved"
        record.update(status="success", artifacts_sha256=artifact_hashes(directory))
        write_record(directory, record)
        progress(100, "分析完成")
        return {"directory": directory, "sample": sample, "result": result, "curve": curve,
                "summary": summary, "record": record, "figures": figures, **science}
    except Exception as error:
        for fig in figures.values():
            if fig is not None:
                plt.close(fig)
        if run is not None:
            run.record.update(status="cancelled" if isinstance(error, Cancelled) else "failed",
                              error=f"{type(error).__name__}: {error}",
                              artifacts_sha256=artifact_hashes(run.directory))
            write_record(run.directory, run.record)
        raise
