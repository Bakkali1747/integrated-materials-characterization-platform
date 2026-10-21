"""Phase 1–2 本地命令行入口；配置与核心计算分离，之后可由 GUI 复用。"""

import argparse
import json
import os
import sys
from pathlib import Path

from export.origin_export import save_figure_bundle

# 缓存放入工作区，避免受限环境写用户全局缓存失败。
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))

import numpy as np

from core.analysis_service import AnalysisConfig, execute
from core.reuse import index_completed_runs, run_key, sha256_file
from export.phase2_export import export_phase2
from export.provenance import artifact_hashes, figure_provenance, json_safe, write_record
from plotting.em_parameters import plot_parameters
from plotting.rl_plot import plot_rl_2d, plot_rl_3d, plot_rl_curve, rl_normalization
from plotting.style import PlotStyle, plt


def analyze(path, *, output="output", name=None, frequency_min=None, frequency_max=None,
            thickness_min=1.0, thickness_max=5.0, thickness_step=0.01, curve_thickness=2.0,
            threshold=-10.0, eab_crossing="linear", style=None, quarter_wave_orders=(1,),
            impedance_tolerance=.1, reuse=False, **parser_options):
    """输入文件、展示单位配置及解析选项；返回唯一结果目录。

    校验、数值计算与数值产物由 core.analysis_service 统一完成；本函数只负责
    命令行特有的图组、Phase 2 导出和成功记录，失败时保存 status=failed 与错误。
    reuse=True 时，若源 SHA-256 与数值配置已有成功运行，直接返回其目录。
    """
    style = style or PlotStyle()
    if not quarter_wave_orders or any(isinstance(n, bool) or not isinstance(n, (int, np.integer)) or n < 1 or n % 2 != 1 for n in quarter_wave_orders):
        raise ValueError("四分之一波长阶数必须为非空正奇数整数列表。")
    if len(set(quarter_wave_orders)) != len(quarter_wave_orders):
        raise ValueError("四分之一波长阶数不能重复。")
    if not np.isfinite(impedance_tolerance) or not 0 < impedance_tolerance < 1:
        raise ValueError("阻抗模长显示容差必须在 0 与 1 之间。")
    if any(not np.isfinite(value) or value <= 0 for value in (style.width, style.height, style.linewidth, style.dpi)):
        raise ValueError("图宽、高、线宽和 dpi 必须有限且大于零。")
    if reuse:
        reuse_configuration = {
            "requested_frequency_range_ghz": [frequency_min, frequency_max],
            "requested_thickness_range_mm": [thickness_min, thickness_max],
            "thickness_step_mm": thickness_step, "curve_thickness_mm": curve_thickness,
            "rl_threshold_db": threshold, "eab_threshold_crossing": eab_crossing,
            "parser_options": dict(parser_options), "quarter_wave_orders": list(quarter_wave_orders),
            "impedance_tolerance": impedance_tolerance}
        cached = index_completed_runs(output).get(
            run_key(name or Path(path).stem, sha256_file(path), reuse_configuration))
        if cached is not None:
            print(f"复用已完成运行：{cached}")
            print("真实样品结果待验证。")
            return cached
    config = AnalysisConfig(path=Path(path), name=name or Path(path).stem, output=Path(output),
                            thickness_min=thickness_min, thickness_max=thickness_max,
                            thickness_step=thickness_step, curve_thickness=curve_thickness,
                            threshold=threshold, frequency_min=frequency_min, frequency_max=frequency_max,
                            eab_crossing=eab_crossing, parser_options=parser_options,
                            entry_point="cli_phase2", name_for_parser=name,
                            extra_configuration={"plot_style": vars(style),
                                                 "quarter_wave_orders": list(quarter_wave_orders),
                                                 "impedance_tolerance": impedance_tolerance})
    run = None
    try:
        run = execute(config)
        sample, result, curve = run.sample, run.result, run.curve
        directory, record, summary = run.directory, run.record, run.summary
        provenance = figure_provenance(record, dpi=style.dpi)
        figures = directory / "figures"
        figures.mkdir()

        def save(fig, filename):
            """保存基本 PNG 验收图；图上标明当前结果仍待验证。"""
            fig.suptitle("PENDING VALIDATION", fontsize=10, color="0.35")
            save_figure_bundle(fig, figures / filename, dpi=style.dpi, provenance=provenance)
            plt.close(fig)

        save(plot_parameters(sample, "permittivity", style), "permittivity.png")
        save(plot_parameters(sample, "permeability", style), "permeability.png")
        if np.isfinite(result.rl_db).all() and np.isfinite(curve.rl_db).all():
            save(plot_rl_curve(curve, style=style, threshold=threshold), "RL_curve.png")
            norm = rl_normalization(result.rl_db)
            save(plot_rl_2d(result, style, norm)[0], "RL_2D.png")
            if len(run.thickness_mm) > 1:
                save(plot_rl_3d(result, style, norm)[0], "RL_3D.png")
            else:
                sample.warnings.append("仅一个厚度点，跳过三维面图。")
            record["rl_color_limits_db"] = [norm.vmin, norm.vmax]
        else:
            sample.warnings.append("RL 存在无限极限值，原始数据已保存，跳过 RL 图以避免自动截断。")
        phase2 = export_phase2(sample, result, curve, directory, save, style, quarter_wave_orders, impedance_tolerance)
        record["phase2"] = phase2
        summary["phase2"] = phase2
        (directory / "summary.json").write_text(json.dumps(json_safe(summary), ensure_ascii=False, indent=2), encoding="utf-8")
        record["status"] = "success"
        record["artifacts_sha256"] = artifact_hashes(directory)
        write_record(directory, record)
        for warning in sample.warnings:
            print(warning)
        print(f"结果目录：{directory.resolve()}")
        print("真实样品结果待验证。")
        return directory
    except Exception as error:
        if run is None:
            raise
        run.record.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        write_record(run.directory, run.record)
        plt.close("all")
        raise


def main():
    """命令行输入配置，调用分析流程；错误返回非零退出码并在终端显示。"""
    parser = argparse.ArgumentParser(description="Phase 1–2 微波吸收分析：结果待真实参考验证")
    parser.add_argument("file")
    parser.add_argument("--name")
    parser.add_argument("--output", default="output")
    parser.add_argument("--frequency-unit", choices=["Hz", "kHz", "MHz", "GHz"])
    parser.add_argument("--imaginary-convention", required=True, choices=["loss", "signed"])
    parser.add_argument("--convention-confirmed", action="store_true", help="仅在外部定义已确认后启用")
    parser.add_argument("--column-map", help="JSON 文件：内部字段 -> 源列名")
    parser.add_argument("--sheet", default=None, help="Excel 工作表名称或 0 起始序号；省略选首表")
    parser.add_argument("--header-row", type=int, default=0, help="Excel 表头行，0 起始；标题行在其之前")
    parser.add_argument("--encoding")
    parser.add_argument("--delimiter", default=",")
    for option, default in (("frequency-min", None), ("frequency-max", None), ("thickness-min", 1.),
                            ("thickness-max", 5.), ("thickness-step", .01), ("curve-thickness", 2.), ("threshold", -10.)):
        parser.add_argument("--" + option, type=float, default=default)
    parser.add_argument("--dpi", type=int, default=600)
    parser.add_argument("--width", type=float, default=7.)
    parser.add_argument("--height", type=float, default=4.8)
    parser.add_argument("--linewidth", type=float, default=1.5)
    parser.add_argument("--cmap", default="viridis")
    parser.add_argument("--eab-crossing", choices=["linear", "sample"], default="linear")
    parser.add_argument("--quarter-wave-orders", nargs="+", type=int, default=[1], help="正奇数阶，例如 1 3 5")
    parser.add_argument("--impedance-tolerance", type=float, default=.1, help="模长 1±容差的显示范围，不是物理判据")
    parser.add_argument("--reuse", action="store_true", help="复用源 SHA-256 与配置相同的已完成运行")
    args = vars(parser.parse_args())
    path = args.pop("file")
    style = PlotStyle(**{key: args.pop(key) for key in ("dpi", "width", "height", "linewidth", "cmap")})
    args["style"] = style
    if args["column_map"]:
        args["column_map"] = json.loads(Path(args["column_map"]).read_text(encoding="utf-8-sig"))
    args["sheet"] = args["sheet"] if args["sheet"] is not None else 0
    try:
        analyze(path, **args)
    except Exception as error:
        print(f"分析失败：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
