"""Phase 1 流程适配；数值、频带和绘图全部调用已有 API。"""

from export.origin_export import save_figure_bundle
from dataclasses import dataclass, field
from pathlib import Path
import json
import numpy as np
import pandas as pd
from core.parser import read_sample
from core.sparameter_parser import read_sparameters
from core.electromagnetic import make_complex
from core.units import thickness_grid
from core.rl_calculator import scan_rl, minimum_points
from core.eab import summarize_bandwidths, absorption_bands
from export.provenance import new_run, write_record, artifact_hashes, json_safe
from plotting.em_parameters import plot_parameters
from plotting.rl_plot import plot_rl_curve, plot_rl_2d
from plotting.style import PlotStyle, plt
from application_paths import user_data_root

ROOT = user_data_root()
SUPPORTED = {".csv", ".xlsx", ".xls", ".memp", ".sdat"}
PENDING = "pending_imaginary_convention_and_commercial_reference"


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
    parser_options: dict = field(default_factory=lambda: {"imaginary_convention": "loss"})


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
            data = read_sample(path, **parser_options)
            frequency = data.data.frequency_ghz.to_numpy()
            info.update(status="PENDING", parser=data.metadata["parser"])
        info.update(points=len(frequency), frequency=(float(frequency[0]), float(frequency[-1])))
    except Exception as error:
        import logging
        logging.getLogger("microwave.gui").exception("导入失败：%s", path)
        info["error"] = str(error)
    return info


def analyze_request(request, progress=lambda percent, text: None, cancelled=lambda: False):
    """输入不可变任务快照；返回已有模型、摘要、Figure 与追溯目录。

    只编排正式 API；后台生成 Agg Figure，完成后才交给主线程的 Qt Canvas。
    取消在阶段边界生效，不中断一次数值调用或正在写入的文件。
    """
    r = request
    config = {"entry_point": "gui_phase1", "requested_frequency_range_ghz": [r.frequency_min, r.frequency_max],
              "requested_thickness_range_mm": [r.thickness_min, r.thickness_max],
              "thickness_step_mm": r.thickness_step, "curve_thickness_mm": r.curve_thickness,
              "rl_threshold_db": r.threshold, "eab_threshold_crossing": "linear",
              "parser_options": r.parser_options, "figure_dpi": r.dpi, "full_science": r.full_science,
              "quick_preview": r.quick_preview}
    directory, record = new_run(r.output, r.name, r.path, config)
    figures = {}

    def checkpoint(percent, message):
        if cancelled():
            raise Cancelled("已取消；已写入结果保留，当前运行不标记为成功。")
        progress(percent, message)

    try:
        checkpoint(5, "读取与验证原始数据")
        if not r.name.strip():
            raise ValueError("样品名称不能为空。")
        if not np.isfinite([r.threshold, r.curve_thickness, r.dpi]).all() or r.curve_thickness <= 0 or r.dpi <= 0:
            raise ValueError("曲线厚度和 DPI 必须 > 0，阈值必须有限。")
        for limit in (r.frequency_min, r.frequency_max):
            if limit is not None and (not np.isfinite(limit) or limit <= 0):
                raise ValueError("频率范围必须有限且 > 0 GHz。")
        if r.frequency_min is not None and r.frequency_max is not None and r.frequency_min > r.frequency_max:
            raise ValueError("频率起点不能大于终点。")
        sample = read_sample(r.path, name=r.name, **r.parser_options)
        if record["raw_sha256"] != sample.metadata["sha256"]:
            raise ValueError("分析启动后原始文件发生变化，请重新导入。")
        sample.data.to_csv(directory / "parsed_data.csv", index=False)
        original = sample.data
        selected = np.ones(len(original), dtype=bool)
        if r.frequency_min is not None:
            selected &= original.frequency_ghz >= r.frequency_min
        if r.frequency_max is not None:
            selected &= original.frequency_ghz <= r.frequency_max
        sample.data = original.loc[selected].reset_index(drop=True)
        if len(sample.data) < 2:
            raise ValueError("所选范围少于两个原始频率点。")
        if ((r.frequency_min is not None and r.frequency_min < original.frequency_ghz.iloc[0]) or
                (r.frequency_max is not None and r.frequency_max > original.frequency_ghz.iloc[-1])):
            sample.warnings.append("请求范围超出原始频率，仅使用已有点，不外推。")
        d = thickness_grid(r.thickness_min, r.thickness_max, r.thickness_step)
        f = sample.data.frequency_ghz.to_numpy()
        eps = make_complex(sample.data.eps_real, sample.data.eps_imag)
        mu = make_complex(sample.data.mu_real, sample.data.mu_imag)
        checkpoint(20, "计算 RL 扫描矩阵")
        result = scan_rl(f, eps, mu, d)
        checkpoint(35, "计算连续频带与指定厚度曲线")
        curve = scan_rl(f, eps, mu, [r.curve_thickness])
        standard = summarize_bandwidths(result, -10., "linear")
        selected_bands = standard if r.threshold == -10 else summarize_bandwidths(result, r.threshold, "linear")
        minima = minimum_points(result)
        if any(p["at_frequency_boundary"] or p["at_thickness_boundary"] for p in minima):
            sample.warnings.append("网格最小值触及扫描边界；不能确定范围外的最优值。")
        if any(b["touches_lower_boundary"] or b["touches_upper_boundary"] for e in standard["best_thicknesses"] for b in e["widest_bands"]):
            sample.warnings.append("最大 EAB 触及测量频率边界，仅代表当前范围内带宽。")
        if np.any(result.rl_db > 1e-8):
            sample.warnings.append("存在 RL > 0 dB，请核查虚部定义；未裁剪。")
        summary = {"validation_status": PENDING, "global_minima": minima,
                   "standard_eab": standard, "selected_threshold_bandwidth": selected_bands,
                   "curve_minima": minimum_points(curve),
                   "curve_standard_eab": absorption_bands(f, curve.rl_db[0], -10.),
                   "curve_selected_bandwidth": absorption_bands(f, curve.rl_db[0], r.threshold)}
        record.update({"source": sample.metadata, "parser_version": sample.metadata["parser"],
                       "validation_status": PENDING, "memp_validation_status": "pending" if Path(r.path).suffix.lower() == ".memp" else "not_applicable",
                       "sdat_schema_status": "not_applicable", "warnings": sample.warnings,
                       "selected_source_rows": [sample.metadata["source_rows"][i] for i in np.flatnonzero(selected)],
                       "frequency_range_ghz": [float(f[0]), float(f[-1])], "frequency_points": len(f),
                       "thickness_range_mm": [float(d[0]), float(d[-1])], "thickness_grid_mm": d.tolist(),
                       "thickness_step_mm": r.thickness_step, "rl_threshold_db": r.threshold,
                       "matrix_orientation": "rows=thickness_mm, columns=frequency_ghz",
                       "standard_eab_threshold_db": -10., "eab_threshold_crossing": "linear",
                       "global_minima": minima, "maximum_eab_ghz": standard["maximum_bandwidth_ghz"],
                       "maximum_eab_details": standard["best_thicknesses"]})
        checkpoint(50, "保存原始采样结果与摘要")
        sample.data.to_csv(directory / "electromagnetic_parameters.csv", index=False)
        matrix = pd.DataFrame(result.rl_db, columns=f)
        matrix.insert(0, "thickness_mm", d)
        matrix.to_csv(directory / "RL_matrix.csv", index=False)
        pd.DataFrame({"frequency_ghz": f, "rl_db": curve.rl_db[0]}).to_csv(directory / "RL_curve.csv", index=False)
        pd.DataFrame({"thickness_mm": d, "eab_minus10_db_ghz": [e["maximum_continuous_bandwidth_ghz"] for e in standard["by_thickness"]]}).to_csv(directory / "thickness_summary.csv", index=False)
        (directory / "summary.json").write_text(json.dumps(json_safe(summary), ensure_ascii=False, indent=2), encoding="utf-8")
        style = PlotStyle(dpi=r.dpi)
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
                save_figure_bundle(fig, folder / f"{key}.png", dpi=r.dpi)
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
                save_figure_bundle(fig, folder / filename, dpi=r.dpi)
                plt.close(fig)

            record["phase2"] = export_phase2(sample, result, curve, directory, save_science, style,
                                               render_figures=not r.quick_preview)
            if r.quick_preview:
                for key in ("loss_tangent","attenuation","C0","Cole_Cole","quarter_wave","impedance_curve","impedance"):
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
            (directory / "summary.json").write_text(json.dumps(json_safe(summary), ensure_ascii=False, indent=2), encoding="utf-8")
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
        record.update(status="cancelled" if isinstance(error, Cancelled) else "failed",
                      error=f"{type(error).__name__}: {error}", artifacts_sha256=artifact_hashes(directory))
        write_record(directory, record)
        raise
