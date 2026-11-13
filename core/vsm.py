"""VSM 磁滞回线读取、单位换算与指标计算。

本模块不猜测厂商格式：字段列、磁场单位、磁矩单位和样品质量必须显式提供。
磁场扫描顺序原样保留，不排序、不去重、不补值；背景扣除默认关闭。
"""

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd

from core.parser import decode_text, read_csv_table

FIELD_UNITS = {
    "Oe": 1000.0 / (4.0 * np.pi),          # A/m
    "A/m": 1.0,
    "kA/m": 1000.0,
    "T": 1.0 / (4.0e-7 * np.pi),             # 1/μ0，A/m
    "mT": 1.0 / (4.0e-7 * np.pi) / 1000.0,
}
MOMENT_UNITS = {"emu": 1e-3, "A m^2": 1.0}    # A·m²
SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xls", ".txt"}
BACKGROUND_MODES = {"none", "linear_high_field"}
PARSER_VERSION = "vsm-explicit-columns-v1"

_FIELD_ALIASES = {"field", "fieldoe", "h", "hoe", "magneticfield", "magneticfieldoe", "磁场", "磁场oe"}
_MOMENT_ALIASES = {"moment", "momentemu", "m", "magnetization", "magnetizationemug",
                   "magneticmoment", "磁矩", "磁化强度"}


@dataclass
class VSMData:
    """一次原始 VSM 测量的标准表与解析元数据。"""
    name: str
    frame: pd.DataFrame
    metadata: dict
    warnings: list[str]


def _normalized(value) -> str:
    return "".join(ch for ch in str(value).strip().casefold() if ch not in " _()[]{}·/")


def _pick_column(columns, explicit, aliases, kind):
    """显式列优先；否则只接受唯一别名匹配，绝不按位置猜列。"""
    names = [str(column) for column in columns]
    if explicit:
        if explicit not in names:
            raise ValueError(f"找不到{kind}列 {explicit!r}；现有列：{names}")
        return explicit
    matches = [name for name in names if _normalized(name) in aliases]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"未找到{kind}列；请显式指定。现有列：{names}")
    raise ValueError(f"多列可能为{kind}：{matches}；请显式指定。")


def _excel_frame(raw, suffix, sheet, header_row):
    with pd.ExcelFile(BytesIO(raw), engine="xlrd" if suffix == ".xls" else "openpyxl") as workbook:
        sheet_names = workbook.sheet_names
        if isinstance(sheet, (int, np.integer)) and not isinstance(sheet, bool):
            if not 0 <= int(sheet) < len(sheet_names):
                raise ValueError(f"工作表序号 {int(sheet)} 超出范围；文件共有 {len(sheet_names)} 个工作表：{sheet_names}")
            sheet_name = sheet_names[int(sheet)]
        elif sheet in sheet_names:
            sheet_name = sheet
        else:
            raise ValueError(f"未找到工作表 {sheet!r}；现有工作表：{sheet_names}")
        table = pd.read_excel(workbook, sheet_name=sheet_name, header=None)
    if table.empty:
        raise ValueError(f"Excel 工作表 {sheet_name!r} 为空。")
    if isinstance(header_row, bool) or not isinstance(header_row, (int, np.integer)) or header_row < 0:
        raise ValueError("header_row 必须是非负整数。")
    if header_row >= len(table):
        raise ValueError(f"Excel 表头行 {header_row + 1} 超出工作表行数 {len(table)}。")
    header_values = table.iloc[header_row].tolist()
    header = ["" if pd.isna(value) else str(value).strip() for value in header_values]
    if not any(header):
        raise ValueError(f"Excel 第 {header_row + 1} 行为空，无法作为表头。")
    frame = table.iloc[header_row + 1:].reset_index(drop=True)
    frame.columns = header
    source_rows = list(range(header_row + 2, header_row + 2 + len(frame)))
    return frame, source_rows, {"sheet": sheet_name, "header_row": header_row + 1}


def _source_table(path: Path, *, sheet, header_row, encoding, delimiter):
    """读取文件为字符串表；返回 frame、源行号和解析元数据。"""
    suffix = path.suffix.lower()
    raw = path.read_bytes()
    metadata = {"raw_file": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(),
                "file_size_bytes": len(raw), "parser": PARSER_VERSION}
    if suffix == ".csv" or suffix == ".txt":
        text, actual_encoding = decode_text(raw, encoding)
        actual_delimiter = delimiter if delimiter is not None else ("\t" if suffix == ".txt" else ",")
        frame, source_rows = read_csv_table(text, actual_delimiter)
        metadata.update({"encoding": actual_encoding, "delimiter": actual_delimiter})
    elif suffix in (".xlsx", ".xls"):
        frame, source_rows, excel = _excel_frame(raw, suffix, sheet, header_row)
        metadata.update(excel)
    else:
        raise ValueError(f"VSM 仅支持 .csv / .xlsx / .xls / .txt；不解析 {suffix or '无扩展名'} 文件。")
    return frame, source_rows, metadata


def _numeric_column(frame, column, label, source_rows):
    converted = pd.to_numeric(frame[column], errors="coerce")
    text = frame[column].astype(str).str.strip()
    bad = converted.isna() & frame[column].notna() & (text != "")
    if bad.any():
        locations = [source_rows[i] for i in np.flatnonzero(bad)]
        raise ValueError(f"{label}列 {column!r} 含非数值内容，源行 {locations}。")
    missing = converted.isna()
    if missing.any():
        locations = [source_rows[i] for i in np.flatnonzero(missing)]
        raise ValueError(f"{label}列 {column!r} 存在缺失值，源行 {locations}；不插值、不跳过。")
    values = converted.astype(float)
    if not np.isfinite(values).all():
        locations = [source_rows[i] for i in np.flatnonzero(~np.isfinite(values))]
        raise ValueError(f"{label}列 {column!r} 存在非有限值，源行 {locations}。")
    return values.to_numpy()


def inspect_vsm_table(path, *, sheet=0, header_row=0, encoding=None, delimiter=None) -> dict:
    """读取表头和前几行，供界面选择列名；不做单位换算或科学分析。"""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"原始文件不存在：{path}")
    frame, source_rows, metadata = _source_table(
        path, sheet=sheet, header_row=header_row, encoding=encoding, delimiter=delimiter)
    preview = frame.head(6).fillna("").astype(str)
    return {"columns": [str(column) for column in frame.columns], "preview": preview,
            "source_rows": source_rows[:6], "metadata": metadata, "rows": int(len(frame))}


def suggest_vsm_columns(columns):
    """按唯一别名建议磁场/磁矩列；不唯一时返回 None，由用户显式选择。"""
    field = [name for name in columns if _normalized(name) in _FIELD_ALIASES]
    moment = [name for name in columns if _normalized(name) in _MOMENT_ALIASES]
    return (field[0] if len(field) == 1 else None, moment[0] if len(moment) == 1 else None)


def read_vsm(path, *, name=None, field_column=None, moment_column=None, field_unit=None,
             moment_unit=None, mass_mg=None, sheet=0, header_row=0, encoding=None,
             delimiter=None) -> VSMData:
    """读取 VSM 原始文件；返回标准表、元数据和警告。

    必须显式给出 field_unit 和 moment_unit。mass_mg 为空时不进行质量归一化，
    只报告磁矩。字段列若未显式指定，只接受唯一的别名匹配。
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"原始文件不存在：{path}")
    if field_unit not in FIELD_UNITS:
        raise ValueError("磁场单位必须显式选择 Oe / A/m / kA/m / T / mT。")
    if moment_unit not in MOMENT_UNITS:
        raise ValueError("磁矩单位必须显式选择 emu / A m^2。")
    if mass_mg is not None:
        if isinstance(mass_mg, bool) or not isinstance(mass_mg, (int, float, np.integer, np.floating)):
            raise ValueError("样品质量必须是数值，单位为 mg。")
        if not np.isfinite(float(mass_mg)) or float(mass_mg) <= 0:
            raise ValueError("样品质量必须为有限正数（mg）。")
        mass_mg = float(mass_mg)
    frame, source_rows, metadata = _source_table(
        path, sheet=sheet, header_row=header_row, encoding=encoding, delimiter=delimiter)
    field_name = _pick_column(frame.columns, field_column, _FIELD_ALIASES, "磁场")
    moment_name = _pick_column(frame.columns, moment_column, _MOMENT_ALIASES, "磁矩")
    if field_name == moment_name:
        raise ValueError("磁场列和磁矩列不能是同一列。")

    field_raw = _numeric_column(frame, field_name, "磁场", source_rows)
    moment_raw = _numeric_column(frame, moment_name, "磁矩", source_rows)
    if len(field_raw) < 2:
        raise ValueError("VSM 数据少于 2 个点。")
    if np.ptp(field_raw) <= 0:
        raise ValueError("VSM 磁场范围为 0，无法分析磁滞回线。")
    field_am = field_raw * FIELD_UNITS[field_unit]
    field_oe = field_am / FIELD_UNITS["Oe"]
    if moment_unit == "A m^2":
        moment_am2 = moment_raw * MOMENT_UNITS[moment_unit]
        moment_emu = moment_am2 / 1e-3
    else:
        moment_emu = moment_raw
        moment_am2 = moment_emu * 1e-3
    magnetization = (moment_emu * 1000.0 / mass_mg if mass_mg is not None
                     else np.full(len(moment_emu), np.nan))
    standard = pd.DataFrame({
        "source_row": source_rows,
        "field_oe": field_oe,
        "field_am": field_am,
        "moment_emu": moment_emu,
        "moment_am2": moment_am2,
        "magnetization": magnetization,
    })
    warnings = []
    if len(standard) < 10:
        warnings.append(f"[KNOWN] VSM 数据仅 {len(standard)} 点；磁滞指标可能受采样密度限制。")
    if not (field_oe.min() < 0 < field_oe.max()):
        warnings.append("[KNOWN] 磁场范围未同时覆盖正负场；Hc / Mr 可能不可计算。")
    if mass_mg is None:
        warnings.append("[KNOWN] 未提供样品质量；仅报告磁矩，不进行质量归一化。")
    metadata.update({
        "column_map": {"field": field_name, "moment": moment_name},
        "field_unit": field_unit, "moment_unit": moment_unit,
        "mass_mg": mass_mg, "mass_normalized": mass_mg is not None,
        "source_rows": source_rows,
        "field_range_oe": [float(field_oe.min()), float(field_oe.max())],
        "field_range_original": [float(field_raw.min()), float(field_raw.max())],
    })
    return VSMData(name or path.stem, standard, metadata, warnings)


def _split_branches(field, warnings):
    """按场扫描转向点切分分支；共享转向点，不排序、不插值。"""
    deltas = np.diff(field)
    last_sign = 0
    turns = []
    for index, delta in enumerate(deltas):
        sign = int(np.sign(delta))
        if sign == 0:
            continue
        if last_sign and sign != last_sign:
            turns.append(index)
        last_sign = sign
    boundaries = [0, *turns, len(field) - 1]
    segments = []
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        if end - start < 1:
            continue
        net = field[end] - field[start]
        if np.isclose(net, 0):
            continue
        segments.append((start, end, "ascending" if net > 0 else "descending"))
    if len(segments) == 1:
        warnings.append("[KNOWN] 仅检测到一个单调场扫描分支；无法核对回线闭合，"
                        "Hc / Mr 仅代表该分支。")
    elif len(segments) > 2:
        warnings.append(f"[KNOWN] 检测到 {len(segments)} 个扫描分支；当前只接受一次完整往返，"
                        "指标可能不可计算。")
    elif segments[0][2] == segments[1][2]:
        warnings.append("[KNOWN] 两个扫描分支方向相同；未形成完整往返回线。")
    return segments


def _crossings(field, values):
    """返回 M=0 的线性插值场值；保留精确零点，重复零点去重。"""
    result = []
    for index in range(len(values)):
        if values[index] == 0:
            result.append(float(field[index]))
        if index + 1 < len(values) and values[index] * values[index + 1] < 0:
            x0, x1 = field[index], field[index + 1]
            y0, y1 = values[index], values[index + 1]
            result.append(float(x0 + (0.0 - y0) * (x1 - x0) / (y1 - y0)))
    unique = []
    for value in result:
        if not any(np.isclose(value, kept, rtol=0, atol=1e-12) for kept in unique):
            unique.append(value)
    return unique


def _value_at_zero_field(field, values):
    """返回 H=0 处的插值；分支不跨越零场时返回 None。"""
    exact = [values[index] for index in range(len(field)) if field[index] == 0]
    if exact:
        return float(np.mean(exact))
    for index in range(len(field) - 1):
        if field[index] * field[index + 1] < 0:
            x0, x1 = field[index], field[index + 1]
            y0, y1 = values[index], values[index + 1]
            return float(y0 + (0.0 - x0) * (y1 - y0) / (x1 - x0))
    return None


def _extreme_value(field, values, largest):
    target = field.max() if largest else field.min()
    selected = values[np.isclose(field, target, rtol=0, atol=1e-12)]
    return float(np.mean(selected)) if len(selected) else None


def _linear_background(field, moment, minimum_abs_field, warnings):
    """对正、负高场分别线性拟合后取平均，避免饱和台阶偏置背景斜率。"""
    sides = []
    r_squared_values = []
    for label, mask in (("positive", field >= minimum_abs_field), ("negative", field <= -minimum_abs_field)):
        count = int(mask.sum())
        if count >= 3:
            x, y = field[mask], moment[mask]
            slope, intercept = np.polyfit(x, y, 1)
            residual = y - (slope * x + intercept)
            total = np.sum((y - np.mean(y)) ** 2)
            if total > 0:
                r_squared_values.append(float(1.0 - np.sum(residual ** 2) / total))
            sides.append((label, count, float(slope), float(intercept)))
    if not sides:
        raise ValueError(f"高场背景拟合至少需要一侧 3 个 |H| ≥ {minimum_abs_field:g} Oe 的点。")
    slope = float(np.mean([item[2] for item in sides]))
    intercept = float(np.mean([item[3] for item in sides]))
    count = int(sum(item[1] for item in sides))
    r_squared = float(np.mean(r_squared_values)) if r_squared_values else None
    mask = np.abs(field) >= minimum_abs_field
    moment_span = float(np.ptp(moment[mask])) if np.any(mask) else 0.0
    slope_span = abs(slope) * max(float(np.max(np.abs(field[mask]))) - float(minimum_abs_field), 0.0) \
        if np.any(mask) else 0.0
    # 高场接近常数时 R² 由数值噪声主导，不具解释力；此时不报告也不据此警告。
    if r_squared is not None and moment_span > 0 and slope_span < 0.05 * moment_span:
        r_squared = None
    predicted = slope * field + intercept
    if len(sides) == 1:
        warnings.append(f"[KNOWN] 背景拟合仅使用{'正' if sides[0][0] == 'positive' else '负'}场高场点；"
                        "单侧拟合无法分离饱和项与背景截距。")
    if count < 10:
        warnings.append(f"[KNOWN] 背景拟合仅使用 {count} 个高场点；线性背景假设可能不稳定。")
    if r_squared is not None and r_squared < 0.9:
        warnings.append(f"[KNOWN] 高场线性背景拟合 R²={r_squared:.4g} 偏低；扣除结果需谨慎解释。")
    return {
        "mode": "linear_high_field", "minimum_abs_field_oe": float(minimum_abs_field),
        "slope_emu_per_oe": slope, "intercept_emu": intercept,
        "r_squared": r_squared, "point_count": count, "fit_sides": len(sides),
    }, predicted


def _metric_rows(metrics, unit):
    rows = [
        ("Hc", metrics.get("Hc"), "Oe"),
        ("Hc_A_per_m", metrics.get("Hc_am"), "A/m"),
        ("Hc_positive", metrics.get("Hc_positive_oe"), "Oe"),
        ("Hc_negative", metrics.get("Hc_negative_oe"), "Oe"),
        ("Mr", metrics.get("Mr"), unit),
        ("Mr_positive", metrics.get("Mr_positive"), unit),
        ("Mr_negative", metrics.get("Mr_negative"), unit),
        ("Ms", metrics.get("Ms"), unit),
        ("Ms_positive", metrics.get("Ms_positive"), unit),
        ("Ms_negative", metrics.get("Ms_negative"), unit),
        ("squareness", metrics.get("squareness"), "dimensionless"),
        ("loop_closure", metrics.get("loop_closure"), unit),
        ("saturation_field", metrics.get("saturation_field_oe"), "Oe"),
    ]
    return [(name, value, unit_name) for name, value, unit_name in rows]


def analyze_vsm(data: VSMData, *, background_mode="none", background_min_field_oe=10000.0) -> dict:
    """输入标准 VSM 表；返回指标、分支、背景和质量信息。

    背景扣除与质量归一化都必须由调用方显式选择。指标以归一化磁化强度
    （emu/g，等同 A·m²/kg）为主单位；未提供质量时以 emu 为主单位。
    """
    if background_mode not in BACKGROUND_MODES:
        raise ValueError("background_mode 必须为 none 或 linear_high_field。")
    frame = data.frame
    field = frame["field_oe"].to_numpy(dtype=float)
    moment = frame["moment_emu"].to_numpy(dtype=float)
    if not np.isfinite([background_min_field_oe]).all() or background_min_field_oe <= 0:
        raise ValueError("背景拟合最小 |H| 必须为有限正数（Oe）。")
    warnings = list(data.warnings)
    background = {"mode": "none"}
    corrected = moment.copy()
    if background_mode == "linear_high_field":
        background, predicted = _linear_background(field, moment, float(background_min_field_oe), warnings)
        corrected = moment - predicted
    mass_mg = data.metadata.get("mass_mg")
    mass_g = mass_mg / 1000.0 if mass_mg is not None else None
    values = corrected / mass_g if mass_g else corrected
    unit = "emu/g" if mass_g else "emu"

    branches = _split_branches(field, warnings)
    crossings, zero_values = [], []
    for start, end, direction in branches:
        branch_field = field[start:end + 1]
        branch_values = values[start:end + 1]
        crossings += [(value, direction) for value in _crossings(branch_field, branch_values)]
        zero = _value_at_zero_field(branch_field, branch_values)
        if zero is not None:
            zero_values.append(zero)
    positive_hc = [value for value, _ in crossings if value > 0]
    negative_hc = [abs(value) for value, _ in crossings if value < 0]
    hc_positive = float(np.mean(positive_hc)) if positive_hc else None
    hc_negative = float(np.mean(negative_hc)) if negative_hc else None
    hc_candidates = [value for value in (hc_positive, hc_negative) if value is not None]
    hc = float(np.mean(hc_candidates)) if hc_candidates else None
    mr_positive = [value for value in zero_values if value > 0]
    mr_negative = [abs(value) for value in zero_values if value < 0]
    mr = float(np.mean([abs(value) for value in zero_values])) if zero_values else None
    ms_positive = _extreme_value(field, values, True)
    ms_negative = _extreme_value(field, values, False)
    ms_candidates = [abs(value) for value in (ms_positive, ms_negative) if value is not None]
    ms = float(np.mean(ms_candidates)) if ms_candidates else None
    squareness = (mr / ms) if (mr is not None and ms not in (None, 0)) else None
    max_values = values[np.isclose(field, field.max(), rtol=0, atol=1e-12)]
    min_values = values[np.isclose(field, field.min(), rtol=0, atol=1e-12)]
    closure_parts = []
    if len(max_values) > 1:
        closure_parts.append(float(np.max(max_values) - np.min(max_values)))
    if len(min_values) > 1:
        closure_parts.append(float(np.max(min_values) - np.min(min_values)))
    loop_closure = max(closure_parts) if closure_parts else None
    closure_fraction = (loop_closure / ms) if (loop_closure is not None and ms not in (None, 0)) else None

    if hc is None:
        warnings.append("[KNOWN] 未找到 M=0 的场交叉；Hc 不可计算。")
    if mr is None:
        warnings.append("[KNOWN] 分支未跨越零场；Mr 不可计算。")
    if ms is None:
        warnings.append("[KNOWN] 无法确定最大场处磁化强度；Ms 不可计算。")
    if closure_fraction is not None and closure_fraction > 0.05:
        warnings.append(f"[KNOWN] 回线在最大场处未闭合（差异约 {closure_fraction:.3g} Ms）；"
                        "不能把端点值当作真实饱和值。")
    if field.max() != -field.min():
        warnings.append(f"[KNOWN] 磁场范围不对称（{field.min():g} – {field.max():g} Oe）；"
                        "Hc 平均值可能受偏置影响。")

    metrics = {
        "Hc": hc, "Hc_oe": hc, "Hc_am": (hc * FIELD_UNITS["Oe"]) if hc is not None else None,
        "Hc_positive_oe": hc_positive, "Hc_negative_oe": hc_negative,
        "Mr": mr, "Mr_positive": float(np.mean(mr_positive)) if mr_positive else None,
        "Mr_negative": float(np.mean(mr_negative)) if mr_negative else None,
        "Ms": ms, "Ms_positive": ms_positive, "Ms_negative": ms_negative,
        "squareness": float(squareness) if squareness is not None else None,
        "loop_closure": loop_closure, "loop_closure_fraction": closure_fraction,
        "saturation_field_oe": float(max(abs(field.max()), abs(field.min()))),
        "saturation_field_am": float(max(abs(field.max()), abs(field.min())) * FIELD_UNITS["Oe"]),
        "metrics_unit": unit,
    }
    status = "success" if (hc is not None and mr is not None and ms is not None) else "not_computable"
    quality = {
        "point_count": int(len(field)),
        "branch_count": len(branches),
        "branches": [{"start_index": start, "end_index": end, "direction": direction}
                     for start, end, direction in branches],
        "zero_field_values": zero_values,
        "zero_crossings_oe": [value for value, _ in crossings],
        "duplicate_field_points": int(len(field) - len(np.unique(field))),
        "field_range_oe": [float(field.min()), float(field.max())],
        "moment_range_emu": [float(moment.min()), float(moment.max())],
        "mass_normalized": bool(mass_g),
        "background_mode": background["mode"],
        "clipping": "OFF", "interpolation": "OFF", "sorting": "preserved",
        "status": status, "warnings": warnings,
    }
    return {
        "status": status, "metrics": metrics, "metric_rows": _metric_rows(metrics, unit),
        "background": background, "quality": quality, "warnings": warnings,
        "corrected_moment_emu": corrected, "values": values, "unit": unit,
        "branches": branches,
        "note": ("[COMMON] Hc、Mr 由离散点线性插值；Ms 取最大场处端值，不代表真实饱和。"
                 "背景扣除与质量归一化为显式选项，未进行平滑、裁剪或补值。"),
    }


def load_vsm_metrics(path) -> dict:
    """读取已保存的 VSM 指标 JSON；不重新计算。"""
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))
