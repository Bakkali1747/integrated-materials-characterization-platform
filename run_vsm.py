"""VSM 命令行入口：磁场/磁矩单位、样品质量和背景扣除都必须显式给出。"""

import argparse
import os
import sys
from pathlib import Path

from export.origin_export import save_figure_bundle

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))

from core.vsm_service import VSMConfig, execute, write_vsm_record
from export.provenance import artifact_hashes, figure_provenance
from plotting.style import PlotStyle, plt
from plotting.vsm_plot import make_vsm_figure

VSM_VALIDATION_NOTE = "pending external VSM reference"


def analyze(path, *, output="output", name=None, field_column=None, moment_column=None,
            field_unit="Oe", moment_unit="emu", mass_mg=None, sheet=0, header_row=0,
            encoding=None, delimiter=None, background_mode="none", background_min_field_oe=10000.0,
            style=None):
    """执行一次 VSM 分析并保存图组；返回结果目录。"""
    style = style or PlotStyle()
    config = VSMConfig(path=Path(path), name=name or Path(path).stem, output=Path(output),
                       field_column=field_column, moment_column=moment_column,
                       field_unit=field_unit, moment_unit=moment_unit, mass_mg=mass_mg,
                       sheet=sheet, header_row=header_row, encoding=encoding, delimiter=delimiter,
                       background_mode=background_mode,
                       background_min_field_oe=background_min_field_oe,
                       dpi=style.dpi, entry_point="cli_vsm",
                       extra_configuration={"plot_style": vars(style)})
    result = execute(config)
    figures = result.directory / "figures"
    figures.mkdir()
    provenance = figure_provenance(result.record, dpi=style.dpi)
    keys = ["hysteresis", "hysteresis_zoom"]
    if result.analysis["background"]["mode"] == "linear_high_field":
        keys.append("background")
    for key in keys:
        figure = make_vsm_figure(result.table, result.analysis, key, style.dpi)
        save_figure_bundle(figure, figures / f"{key}.png", dpi=style.dpi, provenance=provenance)
        plt.close(figure)
    result.record.update(figure_output="saved", artifacts_sha256=artifact_hashes(result.directory))
    write_vsm_record(result.directory, result.record)
    metrics = result.analysis["metrics"]
    print(f"VSM 分析结果：{result.directory}")
    print(f"Hc：{metrics['Hc_oe']} Oe / {metrics['Hc_am']} A/m")
    print(f"Mr：{metrics['Mr']} {metrics['metrics_unit']}；Ms：{metrics['Ms']} {metrics['metrics_unit']}")
    print(f"状态：{result.analysis['status']}；验证：{VSM_VALIDATION_NOTE}")
    return result.directory


def main():
    parser = argparse.ArgumentParser(description="VSM 磁滞回线分析（显式单位与质量；支持 Lake Shore .dat）")
    parser.add_argument("file")
    parser.add_argument("--name")
    parser.add_argument("--output", default="output")
    parser.add_argument("--field-column")
    parser.add_argument("--moment-column")
    parser.add_argument("--field-unit", choices=["Oe", "A/m", "kA/m", "T", "mT"],
                        help="非 .dat 文件必填；.dat 从表头读取 Oe")
    parser.add_argument("--moment-unit", choices=["emu", "A m^2"],
                        help="非 .dat 文件必填；.dat 从表头读取 emu")
    parser.add_argument("--mass-mg", type=float,
                        help="样品质量 mg；.dat 留空时使用文件头 Mass(g)")
    parser.add_argument("--background", default="none", choices=["none", "linear_high_field"])
    parser.add_argument("--background-min-field-oe", type=float, default=10000.0)
    parser.add_argument("--sheet", default=0)
    parser.add_argument("--header-row", type=int, default=0)
    parser.add_argument("--encoding")
    parser.add_argument("--delimiter")
    parser.add_argument("--dpi", type=int, default=600)
    args = parser.parse_args()
    is_dat = Path(args.file).suffix.lower() == ".dat"
    if not is_dat and (args.field_unit is None or args.moment_unit is None):
        parser.error("非 .dat 文件必须显式提供 --field-unit 与 --moment-unit。")
    sheet = args.sheet
    try:
        sheet = int(sheet)
    except (TypeError, ValueError):
        pass
    try:
        analyze(args.file, output=args.output, name=args.name, field_column=args.field_column,
                moment_column=args.moment_column, field_unit=args.field_unit or "Oe",
                moment_unit=args.moment_unit or "emu", mass_mg=args.mass_mg, sheet=sheet,
                header_row=args.header_row, encoding=args.encoding, delimiter=args.delimiter,
                background_mode=args.background,
                background_min_field_oe=args.background_min_field_oe,
                style=PlotStyle(dpi=args.dpi))
        return 0
    except Exception as error:
        print(f"VSM 分析失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
