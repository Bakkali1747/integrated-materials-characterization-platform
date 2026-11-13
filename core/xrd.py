"""XRD 文本数据读取、峰检测、Scherrer 尺寸与参考峰匹配。

本模块只支持显式表头或两列（2θ，强度）文本；不解析厂商二进制格式。
不排序、不插值、不裁剪；背景扣除与参考峰匹配均为显式选项。
"""

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from core.parser import decode_text

SUPPORTED_SUFFIXES = {".csv", ".txt", ".xy", ".dat", ".raw"}
PARSER_VERSION = "xrd-delimited-v1"
RAW4_TEXT_PARSER = "bruker-raw4-text-v1"

_TWO_THETA_ALIASES = {"2theta", "2thetadeg", "twotheta", "twothetadeg", "angle", "2θ", "2θdeg",
                      "角度", "衍射角"}
_INTENSITY_ALIASES = {"intensity", "counts", "cps", "i", "psd", "强度", "计数"}
_PHASE_ALIASES = {"phase", "material", "name", "相", "物相"}


@dataclass
class XRDData:
    """一次 XRD 扫描的标准表与解析元数据。"""
    name: str
    frame: pd.DataFrame
    metadata: dict
    warnings: list[str]


def _normalized(value) -> str:
    return "".join(ch for ch in str(value).strip().casefold() if ch not in " _()[]{}·/°")


def _pick_column(columns, explicit, aliases, kind):
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


def _split_line(line, delimiter):
    if delimiter is None:
        return line.split()
    return next(csv.reader([line], delimiter=delimiter, strict=True))


def _raw4_float(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _raw4_sections(lines):
    """解析 Bruker RAW4 文本的节区、VarInfo 块和 [Data] 位置。"""
    sections, var_blocks, block = {}, [], {}
    current = None
    data_index = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if current == "VarInfo":
                var_blocks.append(block)
                block = {}
            current = stripped[1:-1]
            if current == "Data":
                data_index = index
                break
            sections.setdefault(current, {})
            continue
        if current is None or not stripped or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if current == "VarInfo":
            block[key.strip()] = value.strip()
        else:
            sections[current][key.strip()] = value.strip()
    if current == "VarInfo":
        var_blocks.append(block)
    return sections, var_blocks, data_index


def _raw4_table(text):
    """解析 RAW4 文本的 [Data] 段；返回 frame、源行号和元数据。"""
    lines = text.splitlines()
    sections, var_blocks, data_index = _raw4_sections(lines)
    if data_index is None:
        raise ValueError("RAW4 文本缺少 [Data] 段。")
    header_index = None
    for index in range(data_index + 1, len(lines)):
        if lines[index].strip():
            header_index = index
            break
    if header_index is None:
        raise ValueError("RAW4 [Data] 段没有表头。")
    header_line = lines[header_index]
    delimiter = "," if "," in header_line else None

    def split(line):
        if delimiter is None:
            return line.split()
        return next(csv.reader([line], delimiter=delimiter, strict=True))

    header = [token.strip() for token in split(header_line)]
    while header and header[-1] == "":
        header.pop()
    if not header:
        raise ValueError("RAW4 [Data] 段表头为空。")
    rows, source_rows = [], []
    for index in range(header_index + 1, len(lines)):
        stripped = lines[index].strip()
        if not stripped:
            continue
        if stripped.startswith("["):
            break
        try:
            tokens = [token.strip() for token in split(lines[index])]
        except csv.Error as error:
            raise ValueError(f"RAW4 源行 {index + 1} 无法拆分：{error}") from error
        while len(tokens) > len(header) and tokens[-1] == "":
            tokens.pop()
        if len(tokens) != len(header):
            raise ValueError(f"RAW4 源行 {index + 1} 应有 {len(header)} 列，实际 {len(tokens)} 列。")
        rows.append(tokens)
        source_rows.append(index + 1)
    if not rows:
        raise ValueError("RAW4 [Data] 段没有数据行。")
    frame = pd.DataFrame(rows, columns=header)
    range_header = sections.get("RangeHeader", {})
    hardware = sections.get("HardwareConfiguration", {})
    wavelength = _raw4_float(range_header.get("ActuallyUsedLambda"))
    wavelength_source = "ActuallyUsedLambda"
    if wavelength is None:
        wavelength = _raw4_float(hardware.get("AlphaAverage"))
        wavelength_source = "AlphaAverage"
    if wavelength is None:
        wavelength = _raw4_float(hardware.get("Alpha1"))
        wavelength_source = "Alpha1"
    sample_id = None
    for block in var_blocks:
        if str(block.get("Type", "")).strip().upper() == "SAMPLEID":
            sample_id = block.get("Value")
    info = {
        "parser": RAW4_TEXT_PARSER, "has_header": True, "header": header, "raw4_text": True,
        "raw4_header": sections.get("RawHeader", {}), "raw4_hardware": hardware,
        "raw4_range": range_header, "raw4_var_info": var_blocks, "raw4_sample_id": sample_id,
        "wavelength_angstrom": wavelength, "wavelength_source": wavelength_source,
        "start_two_theta": _raw4_float(range_header.get("Start")),
        "step_two_theta": _raw4_float(range_header.get("Increment")),
        "declared_points": _raw4_float(range_header.get("NumberOfMeasuredData")
                                         or range_header.get("Steps")),
    }
    return frame, source_rows, info


def _raw_text_source(path, encoding):
    """读取 RAW4 文本；二进制 .raw 使用同目录同名 .txt 转换文件并记录两者。"""
    raw = path.read_bytes()
    if b"\x00" not in raw:
        try:
            text, actual_encoding = decode_text(raw, encoding)
        except ValueError:
            text = None
        if text is not None and text.lstrip("\ufeff \t\r\n").startswith(";RAW4"):
            return text, {"sha256": hashlib.sha256(raw).hexdigest(), "file_size_bytes": len(raw),
                          "encoding": actual_encoding, "raw_binary": False}
    companion = path.with_suffix(".txt")
    if not companion.is_file():
        raise ValueError("Bruker 二进制 .raw 需要同目录同名 .txt（RAW4 文本转换文件）；"
                         "当前版本不直接解析二进制 RAW。请先用 BrmlToV4Converter 导出 .txt。")
    companion_raw = companion.read_bytes()
    companion_text, companion_encoding = decode_text(companion_raw, encoding)
    if not companion_text.lstrip("\ufeff \t\r\n").startswith(";RAW4"):
        raise ValueError(f"同名转换文件不是 RAW4 文本：{companion}")
    return companion_text, {
        "sha256": hashlib.sha256(raw).hexdigest(), "file_size_bytes": len(raw),
        "encoding": companion_encoding, "raw_binary": True,
        "companion_path": str(companion.resolve()),
        "companion_sha256": hashlib.sha256(companion_raw).hexdigest(),
        "companion_size_bytes": len(companion_raw),
    }


def _text_source(path, encoding):
    if path.suffix.lower() == ".raw":
        return _raw_text_source(path, encoding)
    raw = path.read_bytes()
    text, actual_encoding = decode_text(raw, encoding)
    return text, {"sha256": hashlib.sha256(raw).hexdigest(), "file_size_bytes": len(raw),
                  "encoding": actual_encoding}


def _read_table(text, delimiter, header_row=0):
    """读取带可选表头的文本表；返回 frame、源行号和表头信息。"""
    if text.lstrip("\ufeff \t\r\n").startswith(";RAW4"):
        return _raw4_table(text)
    content = []
    row_numbers = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            tokens = _split_line(line, delimiter)
        except csv.Error as error:
            raise ValueError(f"XRD 源行 {number} 无法按分隔符拆分：{error}") from error
        content.append(tokens)
        row_numbers.append(number)
    if not content:
        raise ValueError("XRD 文件没有数据行。")
    if header_row:
        if isinstance(header_row, bool) or not isinstance(header_row, int) or header_row < 0:
            raise ValueError("header_row 必须是非负整数。")
        if header_row >= len(content):
            raise ValueError(f"header_row={header_row} 超出文件内容行数 {len(content)}。")
        content = content[header_row:]
        row_numbers = row_numbers[header_row:]
        if not content:
            raise ValueError("header_row 之后没有数据。")
    first = content[0]
    try:
        [float(token) for token in first[:2]]
        has_header = False
    except (TypeError, ValueError):
        has_header = True
    if has_header:
        header = [token.strip() for token in first]
        if any(not name for name in header):
            raise ValueError(f"XRD 表头存在空列名：{header}")
        if len(set(header)) != len(header):
            raise ValueError(f"XRD 表头存在重复列名：{header}")
        rows = content[1:]
        source_rows = row_numbers[1:]
    else:
        header = ["two_theta_deg", "intensity"]
        rows = content
        source_rows = row_numbers
        if len(first) != 2:
            raise ValueError("无表头 XRD 文件必须恰好为两列（2θ，强度）；请提供表头与列名。")
    width = len(header)
    for tokens, number in zip(rows, source_rows):
        if len(tokens) != width:
            raise ValueError(f"XRD 源行 {number} 应有 {width} 列，实际 {len(tokens)} 列。")
    frame = pd.DataFrame(rows, columns=header)
    return frame, source_rows, {"has_header": has_header, "header": header}


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


def read_xrd(path, *, name=None, two_theta_column=None, intensity_column=None,
             sheet=0, header_row=0, encoding=None, delimiter=None) -> XRDData:
    """读取 XRD 文件；返回标准表、元数据和警告。

    支持 .csv/.txt/.xy/.dat 和 Bruker RAW4。二进制 .raw 通过同目录同名 .txt
    读取并在元数据中记录两者。表头存在时按列名选择；无表头只接受两列
    （2θ，强度）。2θ 必须严格递增；不排序、不插值、不裁剪。
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"原始文件不存在：{path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"XRD 仅支持 .csv / .txt / .xy / .dat / .raw；不解析 {suffix or '无扩展名'} 文件。")
    if sheet:
        raise ValueError("XRD 文本格式不支持工作表；请选择 .csv/.txt/.xy/.dat/.raw。")
    text, source_meta = _text_source(path, encoding)
    actual_encoding = source_meta["encoding"]
    actual_delimiter = delimiter if delimiter is not None else ("\t" if suffix == ".dat" else
                                                               ("," if suffix == ".csv" else None))
    frame, source_rows, table_info = _read_table(text, actual_delimiter, header_row)
    two_theta_name = _pick_column(frame.columns, two_theta_column, _TWO_THETA_ALIASES, "2θ")
    intensity_name = _pick_column(frame.columns, intensity_column, _INTENSITY_ALIASES, "强度")
    if two_theta_name == intensity_name:
        raise ValueError("2θ 列与强度列不能相同。")
    two_theta = _numeric_column(frame, two_theta_name, "2θ", source_rows)
    intensity = _numeric_column(frame, intensity_name, "强度", source_rows)
    if len(two_theta) < 5:
        raise ValueError("XRD 数据少于 5 个点。")
    declared = table_info.get("declared_points")
    if declared is not None and int(round(declared)) != len(two_theta):
        raise ValueError(f"RAW4 声明 {int(round(declared))} 点，实际读取 {len(two_theta)} 点，"
                         "文件可能不完整。")
    difference = np.diff(two_theta)
    if np.any(difference <= 0):
        bad = [source_rows[i + 1] for i in np.flatnonzero(difference <= 0)]
        raise ValueError(f"2θ 必须严格递增；重复或递减出现在源行 {bad[:20]}；不自动排序。")
    warnings = []
    if len(two_theta) < 50:
        warnings.append(f"[KNOWN] XRD 数据仅 {len(two_theta)} 点；峰宽与 Scherrer 尺寸不确定度较大。")
    if np.any(intensity < 0):
        warnings.append(f"[KNOWN] 强度存在 {int(np.sum(intensity < 0))} 个负值；保留原值，不裁剪。")
    declared_start = table_info.get("start_two_theta")
    if declared_start is not None and abs(float(two_theta[0]) - float(declared_start)) > .01:
        warnings.append(f"[KNOWN] RAW4 声明起始 2θ={declared_start:g}°，实际首点 {two_theta[0]:g}°。")
    declared_step = table_info.get("step_two_theta")
    if declared_step is not None and len(two_theta) > 1:
        actual_step = float(np.median(np.diff(two_theta)))
        if abs(actual_step - float(declared_step)) > max(.001, abs(float(declared_step)) * .02):
            warnings.append(f"[KNOWN] RAW4 声明步长 {declared_step:g}°，实际中位步长 {actual_step:g}°。")
    if source_meta.get("raw_binary"):
        warnings.append("[KNOWN] 二进制 RAW 通过同目录同名 TXT 转换文件读取；原始 .raw 未被修改。")
    standard = pd.DataFrame({
        "source_row": source_rows,
        "two_theta_deg": two_theta,
        "intensity": intensity,
    })
    metadata = {
        "raw_file": str(path.resolve()), "parser": table_info.get("parser", PARSER_VERSION),
        "delimiter": actual_delimiter if actual_delimiter is not None else "whitespace",
        "column_map": {"two_theta": two_theta_name, "intensity": intensity_name},
        "two_theta_unit": "deg", "source_rows": source_rows,
        **source_meta, **table_info,
    }
    metadata["encoding"] = actual_encoding
    return XRDData(name or path.stem, standard, metadata, warnings)


def inspect_xrd_table(path, *, encoding=None, delimiter=None, header_row=0) -> dict:
    """读取表头和前几行，供界面选择列名；不做峰分析。"""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"原始文件不存在：{path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"XRD 仅支持 .csv / .txt / .xy / .dat / .raw；不解析 {suffix or '无扩展名'} 文件。")
    text, source_meta = _text_source(path, encoding)
    actual_delimiter = delimiter if delimiter is not None else ("\t" if suffix == ".dat" else
                                                               ("," if suffix == ".csv" else None))
    frame, source_rows, info = _read_table(text, actual_delimiter, header_row)
    return {"columns": [str(column) for column in frame.columns],
            "rows": int(len(frame)), "preview": frame.head(6).fillna("").astype(str),
            "source_rows": source_rows[:6],
            "metadata": {"encoding": source_meta["encoding"],
                         "delimiter": actual_delimiter if actual_delimiter is not None else "whitespace",
                         **source_meta, **info}}


def suggest_xrd_columns(columns):
    """按唯一别名建议 2θ/强度列；不唯一时返回 None。"""
    two_theta = [name for name in columns if _normalized(name) in _TWO_THETA_ALIASES]
    intensity = [name for name in columns if _normalized(name) in _INTENSITY_ALIASES]
    return (two_theta[0] if len(two_theta) == 1 else None,
            intensity[0] if len(intensity) == 1 else None)


def read_xrd_reference(path, *, two_theta_column=None, intensity_column=None,
                       phase_column=None, encoding=None, delimiter=None) -> list[dict]:
    """读取参考峰列表；返回按物相分组的峰记录。

    参考文件需有表头或恰好两列（2θ，相对强度）；可选 phase 列。
    强度按每个物相的最大值归一化为百分比，不做峰位对齐或插值。
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"参考相文件不存在：{path}")
    text, _ = decode_text(path.read_bytes(), encoding)
    suffix = path.suffix.lower()
    actual_delimiter = delimiter if delimiter is not None else ("\t" if suffix == ".dat" else
                                                               ("," if suffix == ".csv" else None))
    frame, source_rows, _ = _read_table(text, actual_delimiter)
    two_theta_name = _pick_column(frame.columns, two_theta_column, _TWO_THETA_ALIASES, "2θ")
    intensity_name = _pick_column(frame.columns, intensity_column, _INTENSITY_ALIASES, "强度")
    phase_name = None
    if phase_column:
        if phase_column not in frame.columns:
            raise ValueError(f"找不到物相列 {phase_column!r}；现有列：{list(frame.columns)}")
        phase_name = phase_column
    else:
        matches = [str(column) for column in frame.columns if _normalized(column) in _PHASE_ALIASES]
        phase_name = matches[0] if len(matches) == 1 else None
    two_theta = _numeric_column(frame, two_theta_name, "2θ", source_rows)
    intensity = _numeric_column(frame, intensity_name, "强度", source_rows)
    if np.any(intensity < 0):
        raise ValueError("参考峰强度不能为负。")
    phases = frame[phase_name].astype(str).str.strip().to_numpy() if phase_name else np.full(len(frame), "reference")
    if np.any(phases == ""):
        raise ValueError("参考峰物相列存在空值。")
    records = []
    for phase in dict.fromkeys(phases):
        mask = phases == phase
        values = intensity[mask]
        maximum = float(values.max()) if len(values) and values.max() > 0 else 0.0
        for angle, value in zip(two_theta[mask], values):
            records.append({"phase": str(phase), "two_theta_deg": float(angle),
                            "intensity": float(value),
                            "relative_intensity_pct": float(value / maximum * 100.0) if maximum else 0.0})
    if not records:
        raise ValueError("参考相文件没有有效峰。")
    return records


def _local_maxima(values):
    return [index for index in range(1, len(values) - 1)
            if values[index] > values[index - 1] and values[index] >= values[index + 1]]


def _prominence(values, index):
    """返回峰的地形突出度与两侧谷底基线，不使用平滑。"""
    peak = values[index]
    left_min = peak
    cursor = index - 1
    while cursor >= 0 and values[cursor] <= peak:
        left_min = min(left_min, values[cursor])
        cursor -= 1
    right_min = peak
    cursor = index + 1
    while cursor < len(values) and values[cursor] <= peak:
        right_min = min(right_min, values[cursor])
        cursor += 1
    baseline = max(left_min, right_min)
    return float(peak - baseline), float(baseline)


def _fwhm(x, values, index, baseline):
    """在峰值半高处线性插值左右边界；单侧未回落返回 None。"""
    peak = values[index]
    if peak <= baseline:
        return None
    half = baseline + (peak - baseline) / 2.0
    left = None
    cursor = index
    while cursor > 0:
        if values[cursor - 1] <= half:
            x0, x1 = x[cursor - 1], x[cursor]
            y0, y1 = values[cursor - 1], values[cursor]
            left = float(x0 + (half - y0) * (x1 - x0) / (y1 - y0)) if y1 != y0 else float(x1)
            break
        cursor -= 1
    right = None
    cursor = index
    while cursor < len(values) - 1:
        if values[cursor + 1] <= half:
            x0, x1 = x[cursor], x[cursor + 1]
            y0, y1 = values[cursor], values[cursor + 1]
            right = float(x0 + (half - y0) * (x1 - x0) / (y1 - y0)) if y1 != y0 else float(x0)
            break
        cursor += 1
    if left is None or right is None:
        return None
    return float(right - left)


def _linear_background(x, y, left_window, right_window):
    points = []
    for label, window in (("left", left_window), ("right", right_window)):
        low, high = float(window[0]), float(window[1])
        if not np.isfinite([low, high]).all() or low >= high:
            raise ValueError(f"{label} 背景窗口必须为有限且 low < high。")
        mask = (x >= low) & (x <= high)
        count = int(mask.sum())
        if count < 2:
            raise ValueError(f"{label} 背景窗口 {low:g}–{high:g}° 只有 {count} 个点，至少需要 2 个。")
        points.append((float(x[mask].mean()), float(y[mask].mean()), count))
    (x1, y1, count1), (x2, y2, count2) = points
    if x1 == x2:
        raise ValueError("左右背景窗口中心不能相同。")
    slope = (y2 - y1) / (x2 - x1)
    intercept = y1 - slope * x1
    return (slope * x + intercept,
            {"mode": "linear", "left_window_deg": [float(left_window[0]), float(left_window[1])],
             "right_window_deg": [float(right_window[0]), float(right_window[1])],
             "left_center_deg": x1, "right_center_deg": x2,
             "left_points": count1, "right_points": count2,
             "slope": float(slope), "intercept": float(intercept)})


def _match_reference(peaks, reference, tolerance_deg, minimum_relative):
    """把参考峰与实测峰按最近邻贪心匹配；返回每个物相的匹配分数。"""
    phases = {}
    for record in reference:
        if record["relative_intensity_pct"] >= minimum_relative:
            phases.setdefault(record["phase"], []).append(record)
    results = []
    for phase, records in phases.items():
        used = set()
        matches = []
        total_weight = sum(record["relative_intensity_pct"] for record in records) or 1.0
        matched_weight = 0.0
        for record in sorted(records, key=lambda item: item["relative_intensity_pct"], reverse=True):
            candidates = [(abs(peak["two_theta_deg"] - record["two_theta_deg"]), index)
                          for index, peak in enumerate(peaks) if index not in used]
            if not candidates:
                continue
            delta, index = min(candidates)
            if delta <= tolerance_deg:
                used.add(index)
                matched_weight += record["relative_intensity_pct"]
                matches.append({"reference_2theta_deg": record["two_theta_deg"],
                                "observed_2theta_deg": peaks[index]["two_theta_deg"],
                                "delta_deg": float(peaks[index]["two_theta_deg"] - record["two_theta_deg"]),
                                "reference_relative_intensity_pct": record["relative_intensity_pct"],
                                "observed_relative_intensity_pct": peaks[index]["relative_intensity_pct"]})
        results.append({"phase": phase, "score": float(matched_weight / total_weight),
                        "matched_count": len(matches), "reference_count": len(records),
                        "tolerance_deg": float(tolerance_deg), "matches": matches})
    return sorted(results, key=lambda item: item["score"], reverse=True)


def analyze_xrd(data: XRDData, *, wavelength_angstrom=1.5406, k_factor=0.9,
                background_mode="none", background_left=(10.0, 20.0),
                background_right=(70.0, 80.0), min_prominence_relative=0.05,
                min_distance_deg=0.1, smoothing_points=5, reference=None,
                match_tolerance_deg=0.2, reference_min_relative=5.0) -> dict:
    """计算背景、峰位、FWHM、d 间距、Scherrer 尺寸与参考相匹配分数。

    smoothing_points > 1 时只用移动平均曲线做峰检测与 FWHM；原始强度、
    背景扣除结果和导出数据保持不变。
    """
    if background_mode not in {"none", "linear"}:
        raise ValueError("background_mode 必须为 none 或 linear。")
    if isinstance(smoothing_points, bool) or not isinstance(smoothing_points, int) \
            or smoothing_points < 1 or smoothing_points % 2 != 1:
        raise ValueError("峰检测平滑点数必须为正奇数（1 表示不平滑）。")
    if not np.isfinite(wavelength_angstrom) or wavelength_angstrom <= 0:
        raise ValueError("X 射线波长必须为有限正数（Å）。")
    if not np.isfinite(k_factor) or k_factor <= 0:
        raise ValueError("Scherrer 常数 K 必须为有限正数。")
    if not np.isfinite(min_prominence_relative) or not 0 <= min_prominence_relative < 1:
        raise ValueError("最小相对突出度必须在 [0, 1) 内。")
    if not np.isfinite(min_distance_deg) or min_distance_deg < 0:
        raise ValueError("最小峰间距必须为非负有限值。")
    if not np.isfinite(match_tolerance_deg) or match_tolerance_deg <= 0:
        raise ValueError("参考峰匹配容差必须为有限正数。")
    frame = data.frame
    x = frame["two_theta_deg"].to_numpy(dtype=float)
    raw = frame["intensity"].to_numpy(dtype=float)
    warnings = list(data.warnings)
    if background_mode == "linear":
        background, background_info = _linear_background(x, raw, background_left, background_right)
    else:
        background = np.zeros_like(raw)
        background_info = {"mode": "none"}
    corrected = raw - background
    if smoothing_points > 1:
        kernel = np.ones(smoothing_points) / smoothing_points
        detection = np.convolve(np.pad(corrected, (smoothing_points // 2, smoothing_points // 2),
                                       mode="edge"), kernel, mode="valid")
    else:
        detection = corrected
    maximum = float(detection.max())
    if maximum <= 0:
        raise ValueError("背景扣除后最大强度不大于 0，无法检测峰。")
    candidates = []
    for index in _local_maxima(detection):
        prominence, baseline = _prominence(detection, index)
        if prominence < min_prominence_relative * maximum or detection[index] <= 0:
            continue
        candidates.append({"index": index, "two_theta_deg": float(x[index]),
                           "intensity": float(raw[index]), "corrected_intensity": float(corrected[index]),
                           "detection_intensity": float(detection[index]),
                           "prominence": prominence, "baseline": baseline})
    selected = []
    for candidate in sorted(candidates, key=lambda item: item["prominence"], reverse=True):
        if all(abs(candidate["two_theta_deg"] - kept["two_theta_deg"]) >= min_distance_deg for kept in selected):
            selected.append(candidate)
    selected.sort(key=lambda item: item["two_theta_deg"])
    peaks = []
    for candidate in selected:
        index = candidate["index"]
        fwhm = _fwhm(x, detection, index, candidate["baseline"])
        theta = np.radians(candidate["two_theta_deg"] / 2.0)
        d_spacing = float(wavelength_angstrom / (2.0 * np.sin(theta))) if np.sin(theta) > 0 else None
        size_nm = None
        if fwhm is not None and fwhm > 0 and theta > 0:
            beta = np.radians(fwhm)
            size_nm = float(k_factor * wavelength_angstrom / (beta * np.cos(theta)) / 10.0)
        if fwhm is None:
            warnings.append(f"[KNOWN] {candidate['two_theta_deg']:.4g}° 峰的半高宽未在扫描范围内回落；FWHM/尺寸不可计算。")
        peaks.append({
            "two_theta_deg": candidate["two_theta_deg"], "intensity": candidate["intensity"],
            "background": float(background[index]), "corrected_intensity": candidate["corrected_intensity"],
            "detection_intensity": candidate["detection_intensity"],
            "prominence": candidate["prominence"], "baseline": candidate["baseline"],
            "fwhm_deg": fwhm, "d_angstrom": d_spacing, "crystallite_size_nm": size_nm,
            "relative_intensity_pct": float(candidate["prominence"] / maximum * 100.0),
            "at_scan_grid": True,
        })
    if not peaks:
        warnings.append("[KNOWN] 未检测到满足阈值的峰；峰分析不可计算。")
    else:
        peak_max = max(peak["prominence"] for peak in peaks)
        for peak in peaks:
            peak["relative_intensity_pct"] = float(peak["prominence"] / peak_max * 100.0)
    step = float(np.median(np.diff(x)))
    for peak in peaks:
        if peak["fwhm_deg"] is not None and peak["fwhm_deg"] < 2.0 * step:
            warnings.append(f"[KNOWN] {peak['two_theta_deg']:.4g}° 峰 FWHM 接近扫描步长；"
                            "Scherrer 尺寸不确定。")
        if peak["two_theta_deg"] <= x[1] or peak["two_theta_deg"] >= x[-2]:
            warnings.append(f"[KNOWN] {peak['two_theta_deg']:.4g}° 峰接近扫描边界。")
    matching = _match_reference(peaks, reference, match_tolerance_deg, reference_min_relative) if reference else []
    status = "success" if peaks else "not_computable"
    quality = {
        "point_count": int(len(x)), "two_theta_range_deg": [float(x.min()), float(x.max())],
        "step_median_deg": step, "peak_count": len(peaks),
        "background": background_info, "clipping": "OFF", "interpolation": "OFF",
        "sorting": "preserved", "smoothing": "moving_average_for_detection" if smoothing_points > 1 else "OFF",
        "smoothing_points": int(smoothing_points),
        "wavelength_angstrom": float(wavelength_angstrom),
        "k_factor": float(k_factor), "status": status,
    }
    note = ("[COMMON] 峰位为本次扫描网格点；FWHM 在半高处线性插值。"
            "峰检测平滑仅用于检测与 FWHM，原始强度与导出数据未平滑。"
            "Scherrer 尺寸未做仪器展宽校正，仅为表观尺寸。参考相匹配是筛查，不是物相鉴定。")
    return {"status": status, "peaks": peaks, "reference_matching": matching,
            "background": background_info, "quality": quality, "warnings": warnings,
            "corrected_intensity": corrected, "background_intensity": background,
            "note": note}
