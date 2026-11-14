"""XRD 命令行入口：显式波长、峰参数与可选参考相文件。"""

import argparse
import os
import sys
from pathlib import Path

from export.origin_export import save_figure_bundle

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))

from core.xrd_service import XRDConfig, execute, write_xrd_record
from export.provenance import artifact_hashes, figure_provenance
from plotting.style import PlotStyle, plt
from plotting.xrd_plot import make_xrd_figure

XRD_VALIDATION_NOTE = "pending external XRD reference"


def analyze(path, *, output="output", name=None, two_theta_column=None, intensity_column=None,
            header_row=0, encoding=None, delimiter=None, wavelength_angstrom=None, k_factor=0.9,
            background_mode="none", background_left=(10.0, 20.0), background_right=(70.0, 80.0),
            min_prominence_relative=0.05, min_distance_deg=0.1, smoothing_points=5,
            fit_peaks=True, instrument_mode="none", instrument_fwhm_deg=0.0,
            instrument_file=None, reference_path=None, auto_phase_match=True,
            phase_library_path=None, phase_match_tolerance_deg=0.2,
            match_tolerance_deg=0.2, style=None, report=False):
    """执行 XRD 分析并保存图组；返回结果目录。"""
    style = style or PlotStyle()
    config = XRDConfig(path=Path(path), name=name or Path(path).stem, output=Path(output),
                       two_theta_column=two_theta_column, intensity_column=intensity_column,
                       header_row=header_row, encoding=encoding, delimiter=delimiter,
                       wavelength_angstrom=wavelength_angstrom, k_factor=k_factor,
                       background_mode=background_mode, background_left=background_left,
                       background_right=background_right,
                       min_prominence_relative=min_prominence_relative,
                       min_distance_deg=min_distance_deg, smoothing_points=smoothing_points,
                       fit_peaks=fit_peaks, instrument_mode=instrument_mode,
                       instrument_fwhm_deg=instrument_fwhm_deg,
                       instrument_file=Path(instrument_file) if instrument_file else None,
                       reference_path=reference_path, auto_phase_match=auto_phase_match,
                       phase_library_path=Path(phase_library_path) if phase_library_path else None,
                       phase_match_tolerance_deg=phase_match_tolerance_deg,
                       match_tolerance_deg=match_tolerance_deg, dpi=style.dpi, entry_point="cli_xrd",
                       extra_configuration={"plot_style": vars(style)})
    result = execute(config)
    payload = {"status": result.analysis["status"], "peaks": result.analysis["peaks"],
               "reference_matching": result.analysis["reference_matching"],
               "background": result.analysis["background"], "quality": result.analysis["quality"],
               "warnings": result.analysis["warnings"], "note": result.analysis["note"]}
    figures = result.directory / "figures"
    figures.mkdir()
    provenance = figure_provenance(result.record, dpi=style.dpi)
    keys = ["xrd_pattern"] + (["xrd_phase_matches"] if payload["reference_matching"] else [])
    for key in keys:
        figure = make_xrd_figure(result.table, payload, key, style.dpi)
        save_figure_bundle(figure, figures / f"{key}.png", dpi=style.dpi, provenance=provenance)
        plt.close(figure)
    result.record.update(figure_output="saved", artifacts_sha256=artifact_hashes(result.directory))
    write_xrd_record(result.directory, result.record)
    if report:
        from export.xrd_report import export_xrd_report
        export_xrd_report(result.directory, result.directory / "xrd_report", dpi=300)
    print(f"XRD 分析结果：{result.directory}")
    print(f"检测峰：{len(payload['peaks'])}；状态：{payload['status']}；验证：{XRD_VALIDATION_NOTE}")
    for peak in payload["peaks"][:10]:
        print(f"  2theta={peak['two_theta_deg']:.4g} deg  I={peak['relative_intensity_pct']:.4g}%  "
              f"FWHM={peak['fwhm_deg']} deg  d={peak['d_angstrom']} A  D={peak['crystallite_size_nm']} nm")
    for match in (payload.get("library_matches") or [])[:5]:
        print(f"  COD候选 {match.get('formula')} score={match['score']:.3f} "
              f"matched={match['matched_count']}/{match['reference_count']} "
              f"observed={match['observed_coverage']:.1%}")
    return result.directory


def main():
    parser = argparse.ArgumentParser(description="XRD 峰分析（显式波长与峰参数）")
    parser.add_argument("file")
    parser.add_argument("--name")
    parser.add_argument("--output", default="output")
    parser.add_argument("--two-theta-column")
    parser.add_argument("--intensity-column")
    parser.add_argument("--header-row", type=int, default=0)
    parser.add_argument("--encoding")
    parser.add_argument("--delimiter")
    parser.add_argument("--wavelength", type=float,
                        help="X 射线波长 Å；Bruker RAW4 未指定时使用文件头 ActuallyUsedLambda")
    parser.add_argument("--k-factor", type=float, default=0.9)
    parser.add_argument("--background", default="none", choices=["none", "linear"])
    parser.add_argument("--background-left", type=float, nargs=2, default=[10.0, 20.0], metavar=("LOW", "HIGH"))
    parser.add_argument("--background-right", type=float, nargs=2, default=[70.0, 80.0], metavar=("LOW", "HIGH"))
    parser.add_argument("--min-prominence", type=float, default=0.05)
    parser.add_argument("--min-distance", type=float, default=0.1)
    parser.add_argument("--smoothing", type=int, default=5,
                        help="峰检测移动平均点数（正奇数；1=不平滑；原始数据不平滑）")
    parser.add_argument("--no-fit", dest="fit_peaks", action="store_false", default=True,
                        help="关闭 Pseudo-Voigt 峰形拟合，只用半高插值")
    parser.add_argument("--instrument", default="none", choices=["none", "constant", "csv"],
                        help="仪器展宽校正模式")
    parser.add_argument("--instrument-fwhm", type=float, default=0.0,
                        help="常数仪器 FWHM（度）")
    parser.add_argument("--instrument-file", help="仪器展宽曲线 CSV（2θ,FWHM）")
    parser.add_argument("--reference")
    parser.add_argument("--no-auto-phase", dest="auto_phase_match", action="store_false", default=True,
                        help="关闭 COD 物相库自动匹配")
    parser.add_argument("--phase-library", help="COD 物相库 SQLite 路径")
    parser.add_argument("--phase-tolerance", type=float, default=0.2,
                        help="COD 物相库 2θ 匹配容差（度）")
    parser.add_argument("--match-tolerance", type=float, default=0.2)
    parser.add_argument("--dpi", type=int, default=600)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    try:
        analyze(args.file, output=args.output, name=args.name, two_theta_column=args.two_theta_column,
                intensity_column=args.intensity_column, header_row=args.header_row,
                encoding=args.encoding, delimiter=args.delimiter,
                wavelength_angstrom=args.wavelength, k_factor=args.k_factor,
                background_mode=args.background, background_left=tuple(args.background_left),
                background_right=tuple(args.background_right),
                min_prominence_relative=args.min_prominence, min_distance_deg=args.min_distance,
                smoothing_points=args.smoothing, fit_peaks=args.fit_peaks,
                instrument_mode=args.instrument, instrument_fwhm_deg=args.instrument_fwhm,
                instrument_file=args.instrument_file,
                reference_path=args.reference, auto_phase_match=args.auto_phase_match,
                phase_library_path=args.phase_library,
                phase_match_tolerance_deg=args.phase_tolerance,
                match_tolerance_deg=args.match_tolerance,
                style=PlotStyle(dpi=args.dpi), report=args.report)
        return 0
    except Exception as error:
        print(f"XRD 分析失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
