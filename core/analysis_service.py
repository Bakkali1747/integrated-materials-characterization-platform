"""CLI 与 GUI 共用的单样品分析管线；数值、命名和摘要只在这里生成一次。

绘图策略、进度文案与导出方式仍由入口适配层决定；本模块不依赖 Qt。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from core.eab import absorption_bands, cumulative_frequency_coverage, summarize_bandwidths
from core.electromagnetic import make_complex
from core.models import COLUMNS, RLResult, SampleData
from core.parser import read_sample
from core.reuse import ANALYSIS_CACHE_VERSION
from core.rl_calculator import minimum_points, scan_rl
from core.units import thickness_grid
from export.provenance import json_safe, new_run, write_record

PENDING = "pending_imaginary_convention_and_commercial_reference"
CONFIRMED = "pending_commercial_reference"


@dataclass
class AnalysisConfig:
    """一次单样品分析的完整数值与解析配置；不含绘图策略。"""
    path: Path
    name: str
    output: Path
    thickness_min: float = 1.
    thickness_max: float = 5.
    thickness_step: float = .01
    curve_thickness: float = 2.
    threshold: float = -10.
    frequency_min: float | None = None
    frequency_max: float | None = None
    eab_crossing: str = "linear"
    parser_options: dict = field(default_factory=dict)
    entry_point: str = "core"
    extra_configuration: dict = field(default_factory=dict)
    # 命令行未指定 --name 时传 None，让 .memp 使用文件头样品名。
    name_for_parser: str | None = None


@dataclass
class AnalysisRun:
    """核心计算与已保存数值产物的快照；绘图由调用方继续完成。"""
    directory: Path
    record: dict
    sample: object
    result: object
    curve: object
    summary: dict
    standard_eab: dict
    selected_bandwidth: dict
    coverage: dict
    frequencies: np.ndarray
    thickness_mm: np.ndarray


def load_completed_run(directory):
    """读取已完成运行的数值对象，不重新计算；用于显式复用。

    只接受含 RL 矩阵、阻抗矩阵、曲线与摘要的 success 运行；
    不完整或旧格式运行会抛 ValueError，由调用方回退到正常计算。
    """
    directory = Path(directory)
    record = json.loads((directory / "analysis_record.json").read_text(encoding="utf-8"))
    if record.get("status") != "success":
        raise ValueError("只能复用成功的运行。")
    if record.get("analysis_cache_version") != ANALYSIS_CACHE_VERSION:
        raise ValueError("运行由不同分析引擎版本生成，必须重新计算。")
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    for key in ("global_minima", "standard_eab", "selected_threshold_bandwidth", "curve_minima"):
        if key not in summary:
            raise ValueError("运行摘要缺少复用所需字段。")
    frame = pd.read_csv(directory / "electromagnetic_parameters.csv")[COLUMNS]
    sample = SampleData(record.get("sample") or directory.name, frame,
                        dict(record.get("source", {})), list(record.get("warnings", [])))
    matrix = pd.read_csv(directory / "RL_matrix.csv")
    thickness = matrix["thickness_mm"].to_numpy(dtype=float)
    frequency = matrix.columns[1:].astype(float).to_numpy()
    rl_db = matrix.iloc[:, 1:].to_numpy(dtype=float)
    real_path = directory / "impedance_real_matrix.csv"
    imag_path = directory / "impedance_imag_matrix.csv"
    if real_path.is_file() and imag_path.is_file():
        real = pd.read_csv(real_path).iloc[:, 1:].to_numpy(dtype=float)
        imag = pd.read_csv(imag_path).iloc[:, 1:].to_numpy(dtype=float)
        impedance = real + 1j * imag
    else:
        impedance = np.full((len(thickness), len(frequency)), np.nan + 0j)
    result = RLResult(frequency, thickness, rl_db, impedance)
    curve_frame = pd.read_csv(directory / "RL_curve.csv")
    impedance_path = directory / "impedance_curve.csv"
    if impedance_path.is_file():
        impedance_curve = pd.read_csv(impedance_path)
        curve_thickness = float(impedance_curve["thickness_mm"].iloc[0])
        curve_impedance = (impedance_curve["z_real"].to_numpy(dtype=float)
                           + 1j * impedance_curve["z_imag"].to_numpy(dtype=float)).reshape(1, -1)
    else:
        curve_thickness = float(record.get("configuration", {}).get("curve_thickness_mm", 2.))
        curve_impedance = np.full((1, len(curve_frame)), np.nan + 0j)
    curve = RLResult(curve_frame["frequency_ghz"].to_numpy(dtype=float),
                     np.array([curve_thickness]),
                     curve_frame["rl_db"].to_numpy(dtype=float).reshape(1, -1),
                     curve_impedance)
    return AnalysisRun(directory, record, sample, result, curve, summary,
                       summary["standard_eab"], summary["selected_threshold_bandwidth"],
                       summary.get("cumulative_frequency_coverage", {}), frequency, thickness)


def validate_configuration(config):
    """纯输入校验；必须在 new_run 之前调用，避免参数错误留下失败运行目录。"""
    if not isinstance(config.name, str) or not config.name.strip():
        raise ValueError("样品名称不能为空。")
    if config.eab_crossing not in ("linear", "sample"):
        raise ValueError("阈值边界方法必须为 linear 或 sample。")
    if not np.isfinite([config.threshold, config.curve_thickness]).all() or config.curve_thickness <= 0:
        raise ValueError("阈值必须有限；曲线厚度必须 > 0 mm。")
    for limit in (config.frequency_min, config.frequency_max):
        if limit is not None and (not np.isfinite(limit) or limit <= 0):
            raise ValueError("频率范围必须有限且 > 0 GHz。")
    if config.frequency_min is not None and config.frequency_max is not None and config.frequency_min > config.frequency_max:
        raise ValueError("频率起点不能超过终点。")
    thickness_grid(config.thickness_min, config.thickness_max, config.thickness_step)


def _configuration(config):
    return {"entry_point": config.entry_point,
            "requested_frequency_range_ghz": [config.frequency_min, config.frequency_max],
            "requested_thickness_range_mm": [config.thickness_min, config.thickness_max],
            "thickness_step_mm": config.thickness_step, "curve_thickness_mm": config.curve_thickness,
            "rl_threshold_db": config.threshold, "eab_threshold_crossing": config.eab_crossing,
            "parser_options": dict(config.parser_options), **config.extra_configuration}


def execute(config, *, progress=lambda percent, text: None, cancelled=lambda: False, cancel_exception=None):
    """执行校验、读取、RL/EAB 计算并保存数值产物；返回 AnalysisRun。

    cancel_exception 由 GUI 传入，用于把主动取消记录为 cancelled 而不是 failed。
    绘图和最终成功状态由调用方完成后写入，保持 CLI/GUI 图组差异。
    """
    validate_configuration(config)
    d = thickness_grid(config.thickness_min, config.thickness_max, config.thickness_step)
    directory, record = new_run(config.output, config.name, config.path, _configuration(config))

    def checkpoint(percent, message):
        if cancelled():
            raise (cancel_exception or RuntimeError)("已取消；已写入结果保留，当前运行不标记为成功。")
        progress(percent, message)

    try:
        checkpoint(5, "读取与验证原始数据")
        sample = read_sample(config.path, name=config.name_for_parser, **config.parser_options)
        if record["raw_sha256"] != sample.metadata["sha256"]:
            raise ValueError("分析启动后原始文件发生变化，请重新导入。")
        record.update({"sample": sample.name, "source": sample.metadata, "warnings": sample.warnings,
                       "parser_version": sample.metadata["parser"],
                       "validation_status": CONFIRMED if sample.metadata["convention_confirmed"] else PENDING,
                       "memp_validation_status": "pending" if Path(config.path).suffix.lower() == ".memp" else "not_applicable",
                       "sdat_schema_status": "not_applicable"})
        quality = sample.metadata.get("data_quality")
        if quality and (quality["negative_fields"] or quality["near_zero_fields"]):
            (directory / "data_quality.json").write_text(
                json.dumps(json_safe(quality), ensure_ascii=False, indent=2), encoding="utf-8")
        sample.data.to_csv(directory / "parsed_data.csv", index=False)
        original = sample.data
        selected = np.ones(len(original), dtype=bool)
        if config.frequency_min is not None:
            selected &= original.frequency_ghz >= config.frequency_min
        if config.frequency_max is not None:
            selected &= original.frequency_ghz <= config.frequency_max
        sample.data = original.loc[selected].reset_index(drop=True)
        record["selected_source_rows"] = [sample.metadata["source_rows"][i] for i in np.flatnonzero(selected)]
        if ((config.frequency_min is not None and config.frequency_min < original.frequency_ghz.iloc[0]) or
                (config.frequency_max is not None and config.frequency_max > original.frequency_ghz.iloc[-1])):
            sample.warnings.append("[KNOWN] 请求频率范围超出原始数据，仅使用实测范围内已有点，不外推。")
        if len(sample.data) < 2:
            raise ValueError("所选频率范围内少于 2 个点。")
        f = sample.data.frequency_ghz.to_numpy()
        eps = make_complex(sample.data.eps_real, sample.data.eps_imag)
        mu = make_complex(sample.data.mu_real, sample.data.mu_imag)
        checkpoint(20, "计算 RL 扫描矩阵")
        result = scan_rl(f, eps, mu, d)
        if np.any(result.rl_db > 1e-8):
            sample.warnings.append("[KNOWN] 存在 RL > 0 dB，请核查虚部定义、测量及反演；未裁剪。")
        minima = minimum_points(result)
        record.update({"frequency_range_ghz": [float(f[0]), float(f[-1])], "frequency_points": len(f),
                       "thickness_range_mm": [float(d[0]), float(d[-1])], "thickness_step_mm": config.thickness_step,
                       "thickness_points": len(d), "thickness_grid_mm": d.tolist(),
                       "rl_threshold_db": config.threshold,
                       "matrix_orientation": "rows=thickness_mm, columns=frequency_ghz",
                       "minimum_scope": "current scan grid", "global_minima": minima})
        if any(point["at_frequency_boundary"] or point["at_thickness_boundary"] for point in minima):
            sample.warnings.append("[KNOWN] 网格最小值触及频率或厚度边界；不能据此确定扫描范围外的最优值。")
        checkpoint(35, "计算连续频带与指定厚度曲线")
        standard_eab = summarize_bandwidths(result, -10., config.eab_crossing)
        selected_bandwidth = standard_eab if config.threshold == -10 else summarize_bandwidths(
            result, config.threshold, config.eab_crossing)
        coverage = cumulative_frequency_coverage(selected_bandwidth["by_thickness"])
        record.update({"eab_threshold_crossing": config.eab_crossing, "standard_eab_threshold_db": -10.,
                       "maximum_eab_ghz": standard_eab["maximum_bandwidth_ghz"],
                       "maximum_eab_details": standard_eab["best_thicknesses"],
                       "cumulative_frequency_coverage": {**coverage, "threshold_db": config.threshold}})
        if any(band["touches_lower_boundary"] or band["touches_upper_boundary"]
               for entry in standard_eab["best_thicknesses"] for band in entry["widest_bands"]):
            sample.warnings.append("[KNOWN] 最大 EAB 频段触及测量边界，只代表当前频率范围内的带宽。")
        checkpoint(50, "保存原始采样结果与摘要")
        sample.data.to_csv(directory / "electromagnetic_parameters.csv", index=False)
        matrix = pd.DataFrame(result.rl_db, columns=f)
        matrix.insert(0, "thickness_mm", d)
        matrix.to_csv(directory / "RL_matrix.csv", index=False)
        rows = []
        for i, thickness in enumerate(d):
            minimum = float(np.min(result.rl_db[i]))
            rows.append({"thickness_mm": thickness, "rl_min_db": minimum,
                         "rl_min_frequencies_ghz": json.dumps(f[result.rl_db[i] == minimum].tolist()),
                         "eab_minus10_db_ghz": standard_eab["by_thickness"][i]["maximum_continuous_bandwidth_ghz"],
                         "eab_intervals_ghz": json.dumps(standard_eab["by_thickness"][i]["bands"]),
                         "selected_threshold_db": config.threshold,
                         "selected_threshold_max_continuous_bandwidth_ghz": selected_bandwidth["by_thickness"][i]["maximum_continuous_bandwidth_ghz"]})
        pd.DataFrame(rows).to_csv(directory / "thickness_summary.csv", index=False)
        curve = scan_rl(f, eps, mu, [config.curve_thickness])
        pd.DataFrame({"frequency_ghz": f, "rl_db": curve.rl_db[0]}).to_csv(directory / "RL_curve.csv", index=False)
        summary = {"validation_status": record["validation_status"], "global_minima": minima,
                   "standard_eab": standard_eab, "selected_threshold_bandwidth": selected_bandwidth,
                   "cumulative_frequency_coverage": {**coverage, "threshold_db": config.threshold},
                   "curve_minima": minimum_points(curve),
                   "curve_standard_eab": absorption_bands(f, curve.rl_db[0], -10., config.eab_crossing),
                   "curve_selected_bandwidth": absorption_bands(f, curve.rl_db[0], config.threshold, config.eab_crossing)}
        (directory / "summary.json").write_text(json.dumps(json_safe(summary), ensure_ascii=False, indent=2),
                                                encoding="utf-8")
        return AnalysisRun(directory, record, sample, result, curve, summary,
                           standard_eab, selected_bandwidth, coverage, f, d)
    except Exception as error:
        details = getattr(error, "details", None)
        if details is not None:
            try:
                (directory / "validation_errors.json").write_text(
                    json.dumps(json_safe(details), ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
        status = "cancelled" if cancel_exception is not None and isinstance(error, cancel_exception) else "failed"
        record.update({"status": status, "error": f"{type(error).__name__}: {error}"})
        write_record(directory, record)
        raise
