"""XRD 单样品分析运行：读取、峰分析、参考相匹配与追溯产物；不依赖 Qt。"""

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from core import __version__
from core.phase_library import PhaseLibrary, ensure_library
from core.xrd import XRDData, analyze_xrd, read_instrument_broadening, read_xrd, read_xrd_reference
from export.provenance import artifact_hashes, git_state, json_safe

XRD_ANALYSIS_KIND = "xrd_peaks"
XRD_VALIDATION = "pending_external_xrd_reference"


@dataclass
class XRDConfig:
    """一次 XRD 分析的输入与显式峰分析配置。"""
    path: Path
    name: str
    output: Path
    two_theta_column: str | None = None
    intensity_column: str | None = None
    header_row: int = 0
    encoding: str | None = None
    delimiter: str | None = None
    wavelength_angstrom: float | None = None
    k_factor: float = 0.9
    background_mode: str = "none"
    background_left: tuple = (10.0, 20.0)
    background_right: tuple = (70.0, 80.0)
    min_prominence_relative: float = 0.05
    min_distance_deg: float = 0.1
    smoothing_points: int = 5
    fit_peaks: bool = True
    instrument_mode: str = "none"
    instrument_fwhm_deg: float = 0.0
    instrument_file: Path | None = None
    reference_path: Path | None = None
    match_tolerance_deg: float = 0.2
    reference_min_relative: float = 5.0
    auto_phase_match: bool = True
    phase_library_path: Path | None = None
    phase_match_tolerance_deg: float = 0.2
    dpi: int = 600
    entry_point: str = "xrd"
    extra_configuration: dict = field(default_factory=dict)


@dataclass
class XRDResult:
    directory: Path
    record: dict
    data: XRDData
    analysis: dict
    table: pd.DataFrame


def _configuration(config: XRDConfig) -> dict:
    return {
        "two_theta_column": config.two_theta_column,
        "intensity_column": config.intensity_column,
        "header_row": config.header_row,
        "encoding": config.encoding,
        "delimiter": config.delimiter,
        "wavelength_angstrom": config.wavelength_angstrom,
        "k_factor": config.k_factor,
        "background_mode": config.background_mode,
        "background_left_deg": list(config.background_left),
        "background_right_deg": list(config.background_right),
        "min_prominence_relative": config.min_prominence_relative,
        "min_distance_deg": config.min_distance_deg,
        "smoothing_points": config.smoothing_points,
        "fit_peaks": config.fit_peaks,
        "instrument_mode": config.instrument_mode,
        "instrument_fwhm_deg": config.instrument_fwhm_deg,
        "instrument_file": str(config.instrument_file) if config.instrument_file else None,
        "auto_phase_match": config.auto_phase_match,
        "phase_library_path": str(config.phase_library_path) if config.phase_library_path else None,
        "phase_match_tolerance_deg": config.phase_match_tolerance_deg,
        "reference_path": str(config.reference_path) if config.reference_path else None,
        "match_tolerance_deg": config.match_tolerance_deg,
        "reference_min_relative": config.reference_min_relative,
        "figure_dpi": config.dpi,
        **config.extra_configuration,
    }


def validate_configuration(config: XRDConfig) -> None:
    if not isinstance(config.name, str) or not config.name.strip():
        raise ValueError("样品名称不能为空。")
    if config.wavelength_angstrom is not None:
        if not isinstance(config.wavelength_angstrom, (int, float)) or isinstance(config.wavelength_angstrom, bool) \
                or not config.wavelength_angstrom > 0:
            raise ValueError("X 射线波长必须为有限正数（Å）。")
    if not isinstance(config.k_factor, (int, float)) or isinstance(config.k_factor, bool) or not config.k_factor > 0:
        raise ValueError("Scherrer 常数 K 必须为有限正数。")
    if config.background_mode not in {"none", "linear"}:
        raise ValueError("背景扣除模式必须为 none 或 linear。")
    for label, window in (("left", config.background_left), ("right", config.background_right)):
        if len(window) != 2 or not all(isinstance(value, (int, float)) and not isinstance(value, bool)
                                      for value in window):
            raise ValueError(f"{label} 背景窗口必须是两个数值。")
        if window[0] >= window[1]:
            raise ValueError(f"{label} 背景窗口必须 low < high。")
    if not 0 <= config.min_prominence_relative < 1:
        raise ValueError("最小相对突出度必须在 [0, 1) 内。")
    if config.min_distance_deg < 0 or config.match_tolerance_deg <= 0:
        raise ValueError("最小峰间距必须非负，匹配容差必须为正。")
    if isinstance(config.smoothing_points, bool) or not isinstance(config.smoothing_points, int) \
            or config.smoothing_points < 1 or config.smoothing_points % 2 != 1:
        raise ValueError("峰检测平滑点数必须为正奇数（1 表示不平滑）。")
    if not isinstance(config.fit_peaks, bool):
        raise ValueError("fit_peaks 必须为布尔值。")
    if config.instrument_mode not in {"none", "constant", "csv"}:
        raise ValueError("仪器展宽模式必须为 none、constant 或 csv。")
    if not isinstance(config.instrument_fwhm_deg, (int, float)) or isinstance(config.instrument_fwhm_deg, bool) \
            or config.instrument_fwhm_deg < 0:
        raise ValueError("仪器 FWHM 必须为非负数值。")
    if config.instrument_mode == "csv":
        if config.instrument_file is None or not Path(config.instrument_file).is_file():
            raise FileNotFoundError(f"仪器展宽曲线文件不存在：{config.instrument_file}")
    if not isinstance(config.auto_phase_match, bool):
        raise ValueError("auto_phase_match 必须为布尔值。")
    if not np.isfinite(config.phase_match_tolerance_deg) or config.phase_match_tolerance_deg <= 0:
        raise ValueError("物相库匹配容差必须为正数。")
    if not 0 <= config.reference_min_relative <= 100:
        raise ValueError("参考峰最小相对强度必须在 0–100% 内。")
    if config.reference_path is not None and not Path(config.reference_path).is_file():
        raise FileNotFoundError(f"参考相文件不存在：{config.reference_path}")
    if isinstance(config.header_row, bool) or not isinstance(config.header_row, int) or config.header_row < 0:
        raise ValueError("header_row 必须是非负整数。")
    if isinstance(config.dpi, bool) or not isinstance(config.dpi, int) or config.dpi <= 0:
        raise ValueError("DPI 必须为正整数。")


def _now():
    return datetime.now().astimezone()


def write_xrd_record(directory: Path, record: dict) -> None:
    text = json.dumps(json_safe(record), ensure_ascii=False, indent=2, allow_nan=False)
    (directory / "analysis_record.json").write_text(text + "\n", encoding="utf-8")
    peaks = record.get("peak_count", "unavailable")
    lines = [
        f"Analysis kind: {record.get('analysis_kind')}",
        f"Sample: {record.get('sample')}",
        f"Analysis date: {record.get('analysis_date')}",
        f"Software version: {record.get('software_version')}",
        f"Build state: {record.get('build_state')}",
        f"Git commit: {record.get('git', {}).get('commit', 'unavailable')}",
        f"Raw file: {record.get('raw_file')}",
        f"Raw SHA-256: {record.get('raw_sha256')}",
        f"2θ range (deg): {record.get('two_theta_range_deg', 'unavailable')}",
        f"Points: {record.get('point_count', 'unavailable')}",
        f"Wavelength (Angstrom): {record.get('configuration', {}).get('wavelength_angstrom')}",
        f"Detected peaks: {peaks}",
        f"Background: {record.get('background', {}).get('mode', 'none')}",
        "Missing-data interpolation: OFF",
        "Smoothing: OFF",
        f"Validation: {record.get('validation_status')}",
        f"Status: {record.get('status')}",
    ]
    (directory / "analysis_record.txt").write_text("\n".join(lines) + "\n\nComplete record:\n" + text + "\n",
                                                   encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _new_run(config: XRDConfig, raw_sha256: str):
    now = _now()
    run_id = now.strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:12]
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", config.name).strip(" .") or "sample"
    directory = Path(config.output) / ("sample_" + safe_name[:80]) / run_id
    directory.mkdir(parents=True, exist_ok=False)
    state = git_state()
    record = {
        "analysis_kind": XRD_ANALYSIS_KIND, "sample": config.name,
        "analysis_date": now.isoformat(timespec="seconds"), "run_id": run_id,
        "software_version": __version__, "git": state,
        "build_state": "modified" if state["dirty"] is True else "clean" if state["dirty"] is False else "unavailable",
        "raw_file": str(Path(config.path).resolve()), "raw_sha256": raw_sha256,
        "configuration": _configuration(config), "missing_data_interpolation": "OFF",
        "smoothing": "OFF", "clipping": "OFF", "sorting": "preserved",
        "validation_status": XRD_VALIDATION, "status": "started",
    }
    write_xrd_record(directory, record)
    return directory, record


def _analysis_table(data: XRDData, analysis: dict) -> pd.DataFrame:
    table = data.frame.copy()
    table["background"] = analysis["background_intensity"]
    table["corrected_intensity"] = analysis["corrected_intensity"]
    return table


def _analysis_payload(analysis: dict) -> dict:
    return {"status": analysis["status"], "peaks": analysis["peaks"],
            "reference_matching": analysis["reference_matching"],
            "phase_combinations": analysis.get("phase_combinations", []),
            "library_matches": analysis.get("library_matches", []),
            "background": analysis["background"], "quality": analysis["quality"],
            "warnings": analysis["warnings"], "note": analysis["note"]}


def execute(config: XRDConfig, *, progress=lambda percent, text: None,
            cancelled=lambda: False, cancel_exception=None) -> XRDResult:
    """读取、峰分析并保存数值产物；绘图由 GUI/CLI 适配层完成。"""
    validate_configuration(config)
    raw_sha256 = _sha256(Path(config.path))
    directory, record = _new_run(config, raw_sha256)

    def checkpoint(percent, text):
        if cancelled():
            raise (cancel_exception or RuntimeError)("已取消；已写入结果保留，当前运行不标记为成功。")
        progress(percent, text)

    try:
        checkpoint(10, "读取 XRD 原始数据")
        data = read_xrd(config.path, name=config.name, two_theta_column=config.two_theta_column,
                        intensity_column=config.intensity_column, header_row=config.header_row,
                        encoding=config.encoding, delimiter=config.delimiter)
        if data.metadata["sha256"] != raw_sha256:
            raise ValueError("分析启动后原始文件发生变化，请重新导入。")
        wavelength = config.wavelength_angstrom
        wavelength_source = "user"
        if wavelength is None:
            wavelength = data.metadata.get("wavelength_angstrom")
            wavelength_source = data.metadata.get("wavelength_source", "file")
        if wavelength is None:
            raise ValueError("文件未声明 X 射线波长；请显式提供 wavelength_angstrom。")
        record["configuration"].update({"wavelength_angstrom": float(wavelength),
                                        "wavelength_source": wavelength_source})
        reference = read_xrd_reference(config.reference_path, encoding=config.encoding) \
            if config.reference_path else None
        if config.instrument_mode == "constant":
            broadening = {"mode": "constant", "fwhm_deg": float(config.instrument_fwhm_deg)}
        elif config.instrument_mode == "csv":
            broadening = read_instrument_broadening(config.instrument_file, encoding=config.encoding)
        else:
            broadening = {"mode": "none"}
        library = None
        library_error = None
        if config.auto_phase_match:
            checkpoint(30, "准备 COD 物相库")
            try:
                path = config.phase_library_path or ensure_library()
                if path is None:
                    library_error = "未找到 COD 物相库；跳过自动物相匹配。"
                else:
                    library = PhaseLibrary(path)
            except Exception as error:
                library_error = f"COD 物相库不可用：{type(error).__name__}: {error}"
        checkpoint(35, "背景与峰检测")
        try:
            analysis = analyze_xrd(data, wavelength_angstrom=float(wavelength),
                                   k_factor=config.k_factor, background_mode=config.background_mode,
                                   background_left=config.background_left,
                                   background_right=config.background_right,
                                   min_prominence_relative=config.min_prominence_relative,
                                   min_distance_deg=config.min_distance_deg,
                                   smoothing_points=config.smoothing_points,
                                   fit_peaks=config.fit_peaks,
                                   instrument_broadening=broadening, reference=reference,
                                   phase_library=library,
                                   phase_match_tolerance_deg=config.phase_match_tolerance_deg,
                                   match_tolerance_deg=config.match_tolerance_deg,
                                   reference_min_relative=config.reference_min_relative)
        finally:
            if library is not None:
                library.close()
        if library_error:
            analysis["warnings"].append(f"[KNOWN] {library_error}")
        table = _analysis_table(data, analysis)
        table.to_csv(directory / "parsed_data.csv", index=False)
        payload = _analysis_payload(analysis)
        (directory / "xrd_peaks.json").write_text(
            json.dumps(json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
        peak_columns = ["two_theta_deg", "center_deg", "intensity", "background", "corrected_intensity",
                        "prominence", "baseline", "fwhm_interpolated_deg", "fwhm_fit_deg", "fwhm_deg",
                        "eta", "fit_r_squared", "fit_converged", "instrument_fwhm_deg",
                        "corrected_fwhm_deg", "d_angstrom", "crystallite_size_apparent_nm",
                        "crystallite_size_nm", "relative_intensity_pct"]
        pd.DataFrame([{column: peak.get(column) for column in peak_columns} for peak in analysis["peaks"]],
                     columns=peak_columns).to_csv(directory / "xrd_peaks.csv", index=False)
        if analysis["reference_matching"]:
            (directory / "phase_matching.json").write_text(
                json.dumps(json_safe({
                    "phases": analysis["reference_matching"],
                    "combinations": analysis.get("phase_combinations", []),
                    "screening_only": True,
                }), ensure_ascii=False, indent=2),
                encoding="utf-8")
        if analysis.get("library_matches"):
            (directory / "phase_library_matching.json").write_text(
                json.dumps(json_safe({
                    "matches": analysis["library_matches"],
                    "library": analysis["quality"].get("phase_library"),
                    "screening_only": True,
                }), ensure_ascii=False, indent=2),
                encoding="utf-8")
        x = table["two_theta_deg"]
        record.update({
            "status": analysis["status"], "source": data.metadata,
            "parser_version": data.metadata["parser"],
            "two_theta_range_deg": [float(x.min()), float(x.max())],
            "point_count": int(len(x)), "peak_count": len(analysis["peaks"]),
            "quality": analysis["quality"], "background": analysis["background"],
            "reference_matching": analysis["reference_matching"],
            "phase_combinations": analysis.get("phase_combinations", []),
            "library_matches": analysis.get("library_matches", []),
            "warnings": analysis["warnings"],
            "artifacts_sha256": artifact_hashes(directory),
        })
        write_xrd_record(directory, record)
        checkpoint(100, "XRD 峰分析完成")
        return XRDResult(directory, record, data, analysis, table)
    except Exception as error:
        status = "cancelled" if cancel_exception is not None and isinstance(error, cancel_exception) else "failed"
        record.update(status=status, error=f"{type(error).__name__}: {error}",
                      artifacts_sha256=artifact_hashes(directory))
        write_xrd_record(directory, record)
        raise


def load_completed_xrd_run(directory) -> dict:
    """读取已完成的 XRD 运行；只读取保存产物，不重新计算。"""
    directory = Path(directory)
    record = json.loads((directory / "analysis_record.json").read_text(encoding="utf-8"))
    if record.get("status") not in {"success", "not_computable"}:
        raise ValueError("只能载入已完成或不可计算的 XRD 运行。")
    table = pd.read_csv(directory / "parsed_data.csv")
    payload = json.loads((directory / "xrd_peaks.json").read_text(encoding="utf-8"))
    return {"directory": directory, "record": record, "table": table, "metrics": payload}
