"""候选 S 参数独立入口；不改变 .memp 或材料 RL 批量入口。"""

import argparse
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent/".mplconfig"))

import numpy as np
from core import __version__
from core.sparameter_mapping import SParameterMapping, load_sparameter_mapping
from core.sparameter_parser import read_sparameters
from core.sparameters import SParameterTolerances, analyze_sparameters
from export.provenance import json_safe, git_state, artifact_hashes
from plotting.sparameter_plot import plot_sparameter_quantity, plot_rta
from plotting.style import PlotStyle, plt


def write_sparameter_record(directory, record):
    """保存完整 JSON 与可读记录；失败也记录，候选状态始终与计算状态分开。"""
    text = json.dumps(json_safe(record), ensure_ascii=False, indent=2, allow_nan=False)
    for filename in ("analysis_record.json", "analysis_record.txt"):
        (directory/filename).write_text(text+"\n", encoding="utf-8")


def analyze_sparameter_file(path, *, mapping=None, tolerances=None, output="output", name=None,
                            encoding=None, style=None, make_figures=True, schema_file=None):
    """输入真实 sdat、候选映射和容差；返回独立的逐点结果与记录目录。

    输出 CSV/复数 NPZ/QC JSON/metadata XML，禁止覆盖旧运行或裁剪负吸收值。
    """
    path = Path(path)
    mapping = mapping or SParameterMapping()
    tolerances = tolerances or SParameterTolerances()
    style = style or PlotStyle()
    now = datetime.now().astimezone()
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or path.stem).strip(" .") or "sample"
    directory = Path(output).resolve()/"s_parameters"/("sample_"+safe_name[:80])/(now.strftime("%Y%m%dT%H%M%S")+"_"+uuid.uuid4().hex[:12])
    directory.mkdir(parents=True, exist_ok=False)
    record = {"sample": name or path.stem, "analysis_date": now.isoformat(timespec="seconds"),
              "software_version": __version__, "git": git_state(), "raw_file": str(path.resolve()),
              "schema_status": mapping.schema_status, "mapping": mapping.to_dict(), "tolerances": asdict(tolerances),
              "complex_convention": "Sij = real + j*imag", "interpolation": "OFF", "clipping": "OFF",
              "phase_unwrap": "OFF", "status": "started", "validation_status": "candidate_mapping_not_manufacturer_confirmed",
              "plot_style": vars(style), "make_figures": make_figures,
              "note": "S21/S12 manufacturer order remains unconfirmed; numerical screens do not confirm the schema."}
    write_sparameter_record(directory, record)
    try:
        mapping.validate()
        tolerances.validate()
        if any(not np.isfinite(value) or value <= 0 for value in (style.dpi, style.width, style.height, style.linewidth)):
            raise ValueError("图像尺寸、线宽和 dpi 必须为有限正数。")
        record["raw_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        if schema_file:
            record["schema_file"] = str(Path(schema_file).resolve())
            record["schema_file_sha256"] = hashlib.sha256(Path(schema_file).read_bytes()).hexdigest()
        data = read_sparameters(path, mapping, encoding=encoding)
        if record["raw_sha256"] != data.metadata["sha256"]:
            raise ValueError("源文件在读取期间发生变化，请重新运行。")
        table, qc = analyze_sparameters(data.frequency_ghz, data.s_parameters, tolerances)
        table.insert(1, "source_row", data.metadata["source_rows"])
        table.insert(2, "schema_status", mapping.schema_status)
        table.insert(3, "schema_id", mapping.schema_id)
        table.to_csv(directory/"sparameters_by_frequency.csv", index=False)
        data.raw_columns.to_csv(directory/"raw_numeric_columns.csv", index=False)
        np.savez(directory/"sparameters_complex.npz", frequency_ghz=data.frequency_ghz,
                 schema_status=mapping.schema_status, schema_id=mapping.schema_id, **data.s_parameters)
        (directory/"metadata.xml").write_text(data.metadata["metadata_xml"], encoding="utf-8")
        (directory/"quality_checks.json").write_text(json.dumps(json_safe(qc), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        if make_figures:
            figures = directory/"figures"
            figures.mkdir()
            for quantity in ("magnitude", "db", "phase_deg", "RTA"):
                fig = plot_rta(table, style) if quantity == "RTA" else plot_sparameter_quantity(table, quantity, style)
                fig.suptitle(mapping.schema_status + " (not manufacturer-confirmed)", fontsize=9, color="0.35")
                fig.savefig(figures/f"{quantity}.png", dpi=style.dpi)
                plt.close(fig)
        record.update({"status": "success", "source": data.metadata, "frequency_points": len(table),
                       "frequency_range_ghz": [float(data.frequency_ghz[0]), float(data.frequency_ghz[-1])],
                       "frequency_step_range_ghz": [float(np.diff(data.frequency_ghz).min()), float(np.diff(data.frequency_ghz).max())] if len(table)>1 else None,
                       "quality_checks": qc, "artifacts_sha256": artifact_hashes(directory)})
        write_sparameter_record(directory, record)
        print("[KNOWN] schema_status="+mapping.schema_status+"；不是 manufacturer-confirmed。")
        for warning in qc["warnings"]:
            print(warning)
        print(f"S 参数结果：{directory}")
        return directory
    except Exception as error:
        record.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        write_sparameter_record(directory, record)
        plt.close("all")
        raise


def main():
    """命令行加载可替换 schema 和筛查容差，失败返回非零退出码。"""
    parser = argparse.ArgumentParser(description="候选 sdat S 参数分析（不处理 memp）")
    parser.add_argument("file")
    parser.add_argument("--schema", default=str(Path(__file__).resolve().parent/"config"/"sparameter_candidate.json"))
    parser.add_argument("--output", default="output")
    parser.add_argument("--name")
    parser.add_argument("--encoding")
    parser.add_argument("--dpi", type=int, default=600)
    parser.add_argument("--no-figures", action="store_true")
    for option, value in asdict(SParameterTolerances()).items():
        parser.add_argument("--"+option.replace("_", "-"), type=float, default=value)
    args = parser.parse_args()
    try:
        mapping = load_sparameter_mapping(args.schema)
        tolerances = SParameterTolerances(**{key: getattr(args, key) for key in asdict(SParameterTolerances())})
        analyze_sparameter_file(args.file, mapping=mapping, tolerances=tolerances, output=args.output, name=args.name,
                                encoding=args.encoding, style=PlotStyle(dpi=args.dpi), make_figures=not args.no_figures, schema_file=args.schema)
        return 0
    except Exception as error:
        print(f"S 参数分析失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
