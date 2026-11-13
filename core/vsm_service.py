"""VSM 单样品分析运行：读取、计算、保存追溯产物；不依赖 Qt。"""

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from core import __version__
from core.vsm import (
    BACKGROUND_MODES,
    FIELD_UNITS,
    MOMENT_UNITS,
    VSMData,
    analyze_vsm,
    read_vsm,
)
from export.provenance import artifact_hashes, git_state, json_safe

VSM_ANALYSIS_KIND = "vsm_hysteresis"
VSM_VALIDATION = "pending_external_vsm_reference"


@dataclass
class VSMConfig:
    """一次 VSM 分析的输入与显式解析/扣除配置。"""
    path: Path
    name: str
    output: Path
    field_column: str | None = None
    moment_column: str | None = None
    field_unit: str = "Oe"
    moment_unit: str = "emu"
    mass_mg: float | None = None
    mass_from_header: bool = False
    sheet: int | str = 0
    header_row: int = 0
    encoding: str | None = None
    delimiter: str | None = None
    background_mode: str = "none"
    background_min_field_oe: float = 10000.0
    dpi: int = 600
    entry_point: str = "vsm"
    extra_configuration: dict = field(default_factory=dict)


@dataclass
class VSMResult:
    directory: Path
    record: dict
    data: VSMData
    analysis: dict
    table: pd.DataFrame


def _now():
    return datetime.now().astimezone()


def _configuration(config: VSMConfig) -> dict:
    return {
        "field_column": config.field_column,
        "moment_column": config.moment_column,
        "field_unit": config.field_unit,
        "moment_unit": config.moment_unit,
        "mass_mg": config.mass_mg,
        "mass_from_header": config.mass_from_header,
        "sheet": config.sheet,
        "header_row": config.header_row,
        "encoding": config.encoding,
        "delimiter": config.delimiter,
        "background_mode": config.background_mode,
        "background_min_field_oe": config.background_min_field_oe,
        "figure_dpi": config.dpi,
        **config.extra_configuration,
    }


def validate_configuration(config: VSMConfig) -> None:
    """纯输入校验；在创建运行目录之前调用。"""
    if not isinstance(config.name, str) or not config.name.strip():
        raise ValueError("样品名称不能为空。")
    if config.field_unit not in FIELD_UNITS:
        raise ValueError("磁场单位必须为 Oe / A/m / kA/m / T / mT。")
    if config.moment_unit not in MOMENT_UNITS:
        raise ValueError("磁矩单位必须为 emu / A m^2。")
    if config.background_mode not in BACKGROUND_MODES:
        raise ValueError("背景扣除模式必须为 none 或 linear_high_field。")
    if config.mass_mg is not None:
        if isinstance(config.mass_mg, bool) or not isinstance(config.mass_mg, (int, float)):
            raise ValueError("样品质量必须是数值（mg）。")
        if not (config.mass_mg > 0):
            raise ValueError("样品质量必须大于 0 mg。")
    if not isinstance(config.mass_from_header, bool):
        raise ValueError("mass_from_header 必须为布尔值。")
    if isinstance(config.header_row, bool) or not isinstance(config.header_row, int) or config.header_row < 0:
        raise ValueError("header_row 必须是非负整数。")
    if isinstance(config.dpi, bool) or not isinstance(config.dpi, int) or config.dpi <= 0:
        raise ValueError("DPI 必须为正整数。")
    if not (config.background_min_field_oe > 0):
        raise ValueError("背景拟合最小 |H| 必须大于 0 Oe。")


def _new_run(config: VSMConfig, raw_sha256: str):
    now = _now()
    run_id = now.strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:12]
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", config.name).strip(" .") or "sample"
    directory = Path(config.output) / ("sample_" + safe_name[:80]) / run_id
    directory.mkdir(parents=True, exist_ok=False)
    state = git_state()
    record = {
        "analysis_kind": VSM_ANALYSIS_KIND,
        "sample": config.name,
        "analysis_date": now.isoformat(timespec="seconds"),
        "run_id": run_id,
        "software_version": __version__,
        "git": state,
        "build_state": "modified" if state["dirty"] is True else "clean" if state["dirty"] is False else "unavailable",
        "raw_file": str(Path(config.path).resolve()),
        "raw_sha256": raw_sha256,
        "configuration": _configuration(config),
        "missing_data_interpolation": "OFF",
        "clipping": "OFF",
        "sorting": "preserved",
        "validation_status": VSM_VALIDATION,
        "status": "started",
    }
    write_vsm_record(directory, record)
    return directory, record


def write_vsm_record(directory: Path, record: dict) -> None:
    text = json.dumps(json_safe(record), ensure_ascii=False, indent=2, allow_nan=False)
    (directory / "analysis_record.json").write_text(text + "\n", encoding="utf-8")
    metrics = record.get("metrics") or {}
    lines = [
        f"Analysis kind: {record.get('analysis_kind', 'vsm')}",
        f"Sample: {record.get('sample')}",
        f"Analysis date: {record.get('analysis_date')}",
        f"Software version: {record.get('software_version')}",
        f"Build state: {record.get('build_state')}",
        f"Git commit: {record.get('git', {}).get('commit', 'unavailable')}",
        f"Raw file: {record.get('raw_file')}",
        f"Raw SHA-256: {record.get('raw_sha256')}",
        f"Field range (Oe): {record.get('field_range_oe', 'unavailable')}",
        f"Field points: {record.get('field_points', 'unavailable')}",
        f"Hc (Oe): {metrics.get('Hc_oe')}",
        f"Mr: {metrics.get('Mr')} {metrics.get('metrics_unit', '')}",
        f"Ms: {metrics.get('Ms')} {metrics.get('metrics_unit', '')}",
        "Missing-data interpolation: OFF",
        f"Background subtraction: {record.get('background', {}).get('mode', 'none')}",
        f"Mass normalization: {record.get('mass_normalization')}",
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


def _analysis_table(data: VSMData, analysis: dict) -> pd.DataFrame:
    table = data.frame.copy()
    table["background_emu"] = data.frame["moment_emu"].to_numpy() - analysis["corrected_moment_emu"]
    table["corrected_moment_emu"] = analysis["corrected_moment_emu"]
    table["analysis_value"] = analysis["values"]
    return table


def execute(config: VSMConfig, *, progress=lambda percent, text: None,
            cancelled=lambda: False, cancel_exception=None) -> VSMResult:
    """读取、计算并保存 VSM 数值产物；绘图由 GUI/CLI 适配层完成。"""
    validate_configuration(config)
    raw_sha256 = _sha256(Path(config.path))
    directory, record = _new_run(config, raw_sha256)

    def checkpoint(percent, text):
        if cancelled():
            raise (cancel_exception or RuntimeError)("已取消；已写入结果保留，当前运行不标记为成功。")
        progress(percent, text)

    try:
        checkpoint(10, "读取 VSM 原始数据")
        data = read_vsm(config.path, name=config.name, field_column=config.field_column,
                        moment_column=config.moment_column, field_unit=config.field_unit,
                        moment_unit=config.moment_unit, mass_mg=config.mass_mg,
                        mass_from_header=config.mass_from_header,
                        sheet=config.sheet, header_row=config.header_row,
                        encoding=config.encoding, delimiter=config.delimiter)
        if data.metadata["sha256"] != raw_sha256:
            raise ValueError("分析启动后原始文件发生变化，请重新导入。")
        checkpoint(35, "计算磁滞指标与背景")
        analysis = analyze_vsm(data, background_mode=config.background_mode,
                               background_min_field_oe=float(config.background_min_field_oe))
        table = _analysis_table(data, analysis)
        table.to_csv(directory / "parsed_data.csv", index=False)
        metrics = {**analysis["metrics"], "background": analysis["background"],
                   "quality": analysis["quality"], "note": analysis["note"],
                   "status": analysis["status"], "warnings": analysis["warnings"]}
        (directory / "vsm_metrics.json").write_text(
            json.dumps(json_safe(metrics), ensure_ascii=False, indent=2), encoding="utf-8")
        pd.DataFrame(analysis["metric_rows"], columns=["metric", "value", "unit"]).to_csv(
            directory / "vsm_metrics.csv", index=False)
        field = table["field_oe"]
        record.update({
            "status": analysis["status"],
            "source": data.metadata,
            "parser_version": data.metadata["parser"],
            "field_range_oe": [float(field.min()), float(field.max())],
            "field_points": int(len(field)),
            "mass_normalization": bool(data.metadata.get("mass_mg")),
            "mass_mg": data.metadata.get("mass_mg"),
            "background": analysis["background"],
            "metrics": analysis["metrics"],
            "quality": analysis["quality"],
            "warnings": analysis["warnings"],
            "artifacts_sha256": artifact_hashes(directory),
        })
        write_vsm_record(directory, record)
        checkpoint(100, "VSM 指标计算完成")
        return VSMResult(directory, record, data, analysis, table)
    except Exception as error:
        status = "cancelled" if cancel_exception is not None and isinstance(error, cancel_exception) else "failed"
        record.update(status=status, error=f"{type(error).__name__}: {error}",
                      artifacts_sha256=artifact_hashes(directory))
        write_vsm_record(directory, record)
        raise


def load_completed_vsm_run(directory) -> dict:
    """读取已完成的 VSM 运行；只读取保存产物，不重新计算。"""
    directory = Path(directory)
    record = json.loads((directory / "analysis_record.json").read_text(encoding="utf-8"))
    if record.get("status") not in {"success", "not_computable"}:
        raise ValueError("只能载入已完成或不可计算的 VSM 运行。")
    table = pd.read_csv(directory / "parsed_data.csv")
    metrics = json.loads((directory / "vsm_metrics.json").read_text(encoding="utf-8"))
    return {"directory": directory, "record": record, "table": table, "metrics": metrics}
