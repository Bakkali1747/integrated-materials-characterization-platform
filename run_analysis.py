"""Phase 1 本地命令行入口；配置与核心计算分离，之后可由 GUI 复用。"""

import argparse
import json
import os
from pathlib import Path
import sys

# 缓存放入工作区，避免受限环境写用户全局缓存失败。
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))

import numpy as np
import pandas as pd
from core.electromagnetic import make_complex
from core.parser import read_sample
from core.rl_calculator import scan_rl, minimum_points
from core.units import thickness_grid
from export.provenance import new_run, write_record, artifact_hashes, json_safe
from plotting.em_parameters import plot_parameters
from plotting.rl_plot import plot_rl_2d, plot_rl_3d, plot_rl_curve, rl_normalization
from plotting.style import PlotStyle, plt


def analyze(path, *, output="output", name=None, frequency_min=None, frequency_max=None,
            thickness_min=1.0, thickness_max=5.0, thickness_step=0.01, curve_thickness=2.0,
            threshold=-10.0, style=None, **parser_options):
    """输入文件、展示单位配置及解析选项；返回唯一结果目录。

    失败时保存 status=failed 与错误，禁止把部分输出当作成功报告。
    数据只裁选已有频率点，不补值；曲线在指定厚度精确计算，不取最近扫描厚度。
    """
    style = style or PlotStyle()
    configuration = {"requested_frequency_range_ghz": [frequency_min, frequency_max],
                     "requested_thickness_range_mm": [thickness_min, thickness_max],
                     "thickness_step_mm": thickness_step, "curve_thickness_mm": curve_thickness,
                     "rl_threshold_db": threshold, "parser_options": parser_options, "plot_style": vars(style)}
    directory, record = new_run(output, name or Path(path).stem, path, configuration)
    try:
        if not np.isfinite(threshold) or not np.isfinite(curve_thickness) or curve_thickness <= 0:
            raise ValueError("阈值必须有限；曲线厚度必须 > 0 mm。")
        for limit in (frequency_min, frequency_max):
            if limit is not None and (not np.isfinite(limit) or limit <= 0):
                raise ValueError("频率范围必须有限且 > 0 GHz。")
        if frequency_min is not None and frequency_max is not None and frequency_min > frequency_max:
            raise ValueError("频率起点不能超过终点。")
        sample = read_sample(path, name=name, **parser_options)
        record.update({"sample": sample.name, "source": sample.metadata, "warnings": sample.warnings,
                       "validation_status": "pending_commercial_reference" if sample.metadata["convention_confirmed"]
                       else "pending_imaginary_convention_and_commercial_reference"})
        sample.data.to_csv(directory / "parsed_data.csv", index=False)
        data = sample.data
        selected = np.ones(len(data), dtype=bool)
        if frequency_min is not None:
            selected &= data.frequency_ghz >= frequency_min
        if frequency_max is not None:
            selected &= data.frequency_ghz <= frequency_max
        sample.data = data.loc[selected].reset_index(drop=True)
        if len(sample.data) < 2:
            raise ValueError("所选频率范围内少于 2 个点。")
        d = thickness_grid(thickness_min, thickness_max, thickness_step)
        f = sample.data.frequency_ghz.to_numpy()
        eps = make_complex(sample.data.eps_real, sample.data.eps_imag)
        mu = make_complex(sample.data.mu_real, sample.data.mu_imag)
        result = scan_rl(f, eps, mu, d)
        if np.any(result.rl_db > 1e-8):
            sample.warnings.append("[KNOWN] 存在 RL > 0 dB，请核查虚部定义、测量及反演；未裁剪。")
        record.update({"frequency_range_ghz": [float(f[0]), float(f[-1])], "frequency_points": len(f),
                       "thickness_range_mm": [float(d[0]), float(d[-1])], "thickness_step_mm": thickness_step,
                       "thickness_points": len(d), "thickness_grid_mm": d.tolist(),
                       "rl_threshold_db": threshold, "matrix_orientation": "rows=thickness_mm, columns=frequency_ghz",
                       "minimum_scope": "current scan grid", "global_minima": minimum_points(result)})
        sample.data.to_csv(directory / "electromagnetic_parameters.csv", index=False)
        matrix = pd.DataFrame(result.rl_db, columns=f)
        matrix.insert(0, "thickness_mm", d)
        matrix.to_csv(directory / "RL_matrix.csv", index=False)
        rows = []
        for i, thickness in enumerate(d):
            minimum = float(np.min(result.rl_db[i]))
            rows.append({"thickness_mm": thickness, "rl_min_db": minimum,
                         "rl_min_frequencies_ghz": json.dumps(f[result.rl_db[i] == minimum].tolist())})
        pd.DataFrame(rows).to_csv(directory / "thickness_summary.csv", index=False)
        (directory / "summary.json").write_text(json.dumps(json_safe(record["global_minima"]), indent=2), encoding="utf-8")
        curve = scan_rl(f, eps, mu, [curve_thickness])
        pd.DataFrame({"frequency_ghz": f, "rl_db": curve.rl_db[0]}).to_csv(directory / "RL_curve.csv", index=False)
        figures = directory / "figures"
        figures.mkdir()

        def save(fig, filename):
            """保存基本 PNG 验收图；图上标明当前结果仍待验证。"""
            fig.suptitle("PENDING VALIDATION", fontsize=10, color="0.35")
            fig.savefig(figures / filename, dpi=style.dpi)
            plt.close(fig)

        save(plot_parameters(sample, "permittivity", style), "permittivity.png")
        save(plot_parameters(sample, "permeability", style), "permeability.png")
        if np.isfinite(result.rl_db).all() and np.isfinite(curve.rl_db).all():
            save(plot_rl_curve(curve, style=style, threshold=threshold), "RL_curve.png")
            norm = rl_normalization(result.rl_db)
            save(plot_rl_2d(result, style, norm)[0], "RL_2D.png")
            if len(d) > 1:
                save(plot_rl_3d(result, style, norm)[0], "RL_3D.png")
            else:
                sample.warnings.append("仅一个厚度点，跳过三维面图。")
            record["rl_color_limits_db"] = [norm.vmin, norm.vmax]
        else:
            sample.warnings.append("RL 存在无限极限值，原始数据已保存，跳过 RL 图以避免自动截断。")
        record["status"] = "success"
        record["artifacts_sha256"] = artifact_hashes(directory)
        write_record(directory, record)
        for warning in sample.warnings:
            print(warning)
        print(f"结果目录：{directory.resolve()}")
        print("真实样品结果待验证。")
        return directory
    except Exception as error:
        record.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        write_record(directory, record)
        plt.close("all")
        raise


def main():
    """命令行输入配置，调用分析流程；错误返回非零退出码并在终端显示。"""
    parser = argparse.ArgumentParser(description="Phase 1 微波吸收分析：结果待真实参考验证")
    parser.add_argument("file")
    parser.add_argument("--name")
    parser.add_argument("--output", default="output")
    parser.add_argument("--frequency-unit", choices=["Hz", "kHz", "MHz", "GHz"])
    parser.add_argument("--imaginary-convention", required=True, choices=["loss", "signed"])
    parser.add_argument("--convention-confirmed", action="store_true", help="仅在外部定义已确认后启用")
    parser.add_argument("--column-map", help="JSON 文件：内部字段 -> 源列名")
    parser.add_argument("--sheet", default=None, help="Excel 工作表名称；省略选首表")
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
