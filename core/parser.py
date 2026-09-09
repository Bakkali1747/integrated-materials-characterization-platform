"""读取已知文本结构；未知扩展名或列结构必须拒绝，不能猜测。"""

from io import BytesIO, StringIO
from pathlib import Path
import csv
import hashlib
import re
import numpy as np
import pandas as pd
from core.models import COLUMNS, SampleData
from core.validation import validate_data

MEMP_HEADER = ["频率(GHz)", "介电实部", "介电虚部", "磁导实部", "磁导虚部"]


def read_csv_table(text, delimiter):
    """输入文本及分隔符；返回严格矩形表和实际源行号，拒绝多/少列及重复表头。"""
    reader = csv.reader(StringIO(text), delimiter=delimiter, strict=True)
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("CSV 文件为空。") from None
    if not header or len(set(header)) != len(header):
        raise ValueError("CSV 表头为空或存在重复列名。")
    rows, source_rows = [], []
    for tokens in reader:
        if len(tokens) != len(header):
            raise ValueError(f"CSV 源行 {reader.line_num} 应有 {len(header)} 列，实际 {len(tokens)} 列。")
        rows.append(tokens)
        source_rows.append(reader.line_num)
    return pd.DataFrame(rows, columns=header), source_rows


def decode_text(raw, encoding=None):
    """输入文件字节及可选编码；返回文本和实际编码，严格解码不替换坏字节。"""
    if b"\x00" in raw:
        raise ValueError("检测到 NUL 字节，当前解析器不支持该二进制或 UTF-16 文件。")
    candidates = [encoding] if encoding else ["utf-8-sig", "gbk"]
    for candidate in candidates:
        try:
            return raw.decode(candidate, errors="strict"), candidate
        except UnicodeDecodeError:
            continue
    raise ValueError("文本编码无法可靠解码，请显式提供编码或格式说明。")


def read_memp(text):
    """输入已解码文本；返回五列表、元数据、源行号。

    仅支持本次已观察到的中文表头结构；不推断文件虚部的符号语义。
    """
    lines = text.splitlines()
    header_index = None
    for index, line in enumerate(lines):
        if line.split() == MEMP_HEADER:
            header_index = index
            break
    if header_index is None:
        raise ValueError("未知 .memp 表头，拒绝按列位置猜测。")
    metadata = {}
    for line in lines[:header_index]:
        if "：" in line:
            key, value = line.split("：", 1)
            metadata[key.strip()] = value.strip()
    declared = re.fullmatch(r"([\d.]+)~([\d.]+)GHz,(\d+)", metadata.get("测试频率", ""))
    if declared is None:
        raise ValueError(".memp 缺少可识别的频率范围与点数声明。")
    rows, source_rows = [], []
    for index in range(header_index + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            if any(t.strip() for t in lines[index + 1:]):
                raise ValueError(f".memp 源行 {index + 1} 数据段内部为空行。")
            continue
        # 按 tab 拆分才能保留中间的缺失单元格。
        tokens = line.split("\t") if "\t" in line else line.split()
        if len(tokens) != 5:
            raise ValueError(f".memp 源行 {index + 1} 应有 5 列，实际 {len(tokens)} 列。")
        rows.append([token.strip() for token in tokens])
        source_rows.append(index + 1)
    if len(rows) != int(declared[3]):
        raise ValueError(f".memp 声明 {declared[3]} 点，实际 {len(rows)} 点，文件可能不完整。")
    frame = pd.DataFrame(rows, columns=COLUMNS)
    try:
        endpoints = [float(rows[0][0]), float(rows[-1][0])]
    except (ValueError, IndexError):
        raise ValueError(".memp 频率首尾无效。") from None
    if not np.allclose(endpoints, [float(declared[1]), float(declared[2])], rtol=0, atol=1e-9):
        raise ValueError(".memp 实际频率首尾与声明不符，文件可能不完整。")
    return frame, metadata, source_rows


def read_sample(path, *, name=None, frequency_unit=None, imaginary_convention=None,
                convention_confirmed=False, column_map=None, sheet=0, encoding=None, delimiter=","):
    """输入只读文件路径及显式解析配置；返回 SampleData。

    imaginary_convention='loss' 表示文件是损耗系数；'signed' 表示 e^(jωt)
    约定下 Python 复数的带符号虚部，需先取负号转为内部损耗系数。
    convention_confirmed=False 时即使选择一种约定，结果也必须标为待验证。
    column_map 方向为：内部字段名 -> 文件列名。频率统一为 GHz。
    """
    path = Path(path)
    if not isinstance(convention_confirmed, bool):
        raise ValueError("convention_confirmed 必须为布尔值 true/false，不能使用字符串。")
    raw = path.read_bytes()
    suffix = path.suffix.lower()
    metadata = {"raw_file": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(),
                "file_size_bytes": len(raw), "parser": "explicit-columns-v1"}
    if imaginary_convention not in ("loss", "signed"):
        raise ValueError("必须显式选择 imaginary_convention=loss 或 signed；不能猜测虚部定义。")
    if suffix == ".memp":
        text, actual_encoding = decode_text(raw, encoding)
        frame, header, source_rows = read_memp(text)
        if frequency_unit not in (None, "GHz"):
            raise ValueError(".memp 表头明确为 GHz，与指定频率单位冲突。")
        if column_map is not None:
            raise ValueError("已识别 .memp 使用固定表头，不接受覆盖列映射。")
        frequency_unit = "GHz"
        metadata.update({"encoding": actual_encoding, "header": header,
                         "column_map": dict(zip(COLUMNS, MEMP_HEADER)), "parser": "observed-memp-v1"})
        name = name or header.get("样品名称")
    elif suffix in (".csv", ".xlsx"):
        if suffix == ".csv":
            text, actual_encoding = decode_text(raw, encoding)
            frame, source_rows = read_csv_table(text, delimiter)
            metadata.update({"encoding": actual_encoding, "delimiter": delimiter})
        else:
            with pd.ExcelFile(BytesIO(raw), engine="openpyxl") as workbook:
                sheet_name = workbook.sheet_names[sheet] if isinstance(sheet, int) else sheet
                table = pd.read_excel(workbook, sheet_name=sheet_name, header=None)
            if table.empty:
                raise ValueError("Excel 工作表为空。")
            header = table.iloc[0].tolist()
            if len(set(header)) != len(header):
                raise ValueError("Excel 存在重复列名，拒绝自动重命名。")
            frame = table.iloc[1:].reset_index(drop=True)
            frame.columns = header
            source_rows = list(range(2, len(frame) + 2))
            metadata["sheet"] = sheet_name
        mapping = column_map or {col: col for col in COLUMNS}
        if set(mapping) != set(COLUMNS) or len(set(mapping.values())) != 5:
            raise ValueError("列映射必须为五个内部字段指定五个不同源列。")
        missing = set(mapping.values()) - set(frame.columns)
        if missing:
            raise ValueError(f"缺少源列 {sorted(missing)}；请提供显式列映射。")
        frame = frame[[mapping[col] for col in COLUMNS]].copy()
        frame.columns = COLUMNS
        metadata["column_map"] = mapping
        if frequency_unit is None:
            if mapping["frequency_ghz"] == "frequency_ghz":
                frequency_unit = "GHz"
            else:
                raise ValueError("非标准频率列必须显式提供单位 Hz/kHz/MHz/GHz。")
    else:
        raise ValueError(f"尚不支持 {suffix}；.sdat 列定义待确认，禁止猜测。")
    factors = {"Hz": 1e-9, "kHz": 1e-6, "MHz": 1e-3, "GHz": 1.0}
    if frequency_unit not in factors:
        raise ValueError("频率单位必须为 Hz/kHz/MHz/GHz。")
    name = name or path.stem
    for col in COLUMNS:
        converted = pd.to_numeric(frame[col], errors="coerce")
        bad = converted.isna() & frame[col].notna() & (frame[col].astype(str).str.strip() != "")
        if bad.any():
            locations = [source_rows[i] for i in np.flatnonzero(bad)]
            raise ValueError(f"样品 {name} 的 {col} 包含非数值内容，源行 {locations}。")
        frame[col] = converted.astype(float)
    frame["frequency_ghz"] *= factors[frequency_unit]
    if imaginary_convention == "signed":
        frame[["eps_imag", "mu_imag"]] *= -1
    warnings = validate_data(frame, name, source_rows)
    if not convention_confirmed:
        warnings.insert(0, "[KNOWN] 文件虚部定义待确认；当前采用显式临时假设，真实数据结果待验证。")
    metadata.update({"source_rows": source_rows, "raw_frequency_unit": frequency_unit,
                     "imaginary_convention": imaginary_convention,
                     "convention_confirmed": convention_confirmed,
                     "imaginary_conversion": "identity" if imaginary_convention == "loss" else "negate once"})
    return SampleData(name, frame, metadata, warnings)
