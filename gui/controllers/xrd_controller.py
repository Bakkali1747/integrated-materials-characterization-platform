"""XRD GUI 适配；数值计算在 core.xrd_service，本层只绘图与保存。"""

from core.xrd_service import XRDConfig, execute, load_completed_xrd_run, write_xrd_record
from export.origin_export import save_figure_bundle
from export.provenance import artifact_hashes, figure_provenance
from plotting.style import plt
from plotting.xrd_plot import make_xrd_figure

FIGURE_KEYS = ("xrd_pattern", "xrd_phase_matches")


class Cancelled(Exception):
    """协作式取消；只在阶段之间停止，不删除已保存数据。"""


def xrd_figure(result, key, dpi=600, *, compact=False):
    return make_xrd_figure(result["table"], result["metrics"], key, dpi, compact=compact)


def _figure_keys(analysis):
    keys = ["xrd_pattern"]
    if analysis.get("reference_matching"):
        keys.append("xrd_phase_matches")
    return keys


def analyze_xrd_request(config: XRDConfig, progress=lambda percent, text: None, cancelled=lambda: False):
    """执行 XRD 核心分析、保存图组，并返回 GUI 快照。"""
    result = execute(config, progress=progress, cancelled=cancelled, cancel_exception=Cancelled)
    payload = {"status": result.analysis["status"], "peaks": result.analysis["peaks"],
               "reference_matching": result.analysis["reference_matching"],
               "phase_combinations": result.analysis.get("phase_combinations", []),
               "background": result.analysis["background"], "quality": result.analysis["quality"],
               "warnings": result.analysis["warnings"], "note": result.analysis["note"]}
    figures = {}
    folder = result.directory / "figures"
    folder.mkdir()
    provenance = figure_provenance(result.record, dpi=config.dpi)
    for index, key in enumerate(_figure_keys(payload)):
        if cancelled():
            raise Cancelled("XRD 绘图已取消；已保存产物保留。")
        progress(80 + index * 5, f"绘制 {key}")
        figure = xrd_figure({"table": result.table, "metrics": payload}, key, config.dpi)
        figures[key] = figure
        save_figure_bundle(figure, folder / f"{key}.png", dpi=config.dpi, provenance=provenance)
        plt.close(figure)
    result.record.update(figure_output="saved", artifacts_sha256=artifact_hashes(result.directory))
    write_xrd_record(result.directory, result.record)
    progress(100, "XRD 分析完成")
    return {"directory": result.directory, "record": result.record, "data": result.data,
            "table": result.table, "metrics": payload, "figures": figures}


def load_xrd_request(directory):
    """读取已登记 XRD 运行；图按需生成，不重新计算。"""
    saved = load_completed_xrd_run(directory)
    return {"directory": saved["directory"], "record": saved["record"], "table": saved["table"],
            "metrics": saved["metrics"],
            "figures": {key: None for key in _figure_keys(saved["metrics"])}}


def _fmt_fit(value):
    return "—" if value is None else f"{float(value):.6g}"


def xrd_summary_text(record, metrics):
    """生成界面摘要；缺失值明确写不可计算。"""
    background = metrics.get("background") or {}
    quality = metrics.get("quality") or {}
    instrument = quality.get("instrument_broadening") or {}
    peaks = metrics.get("peaks") or []
    lines = [
        f"样品：{record.get('sample')}",
        f"来源：{record.get('raw_file')}",
        f"2θ 范围：{record.get('two_theta_range_deg')}°；{record.get('point_count')} 点",
        f"波长：{record.get('configuration', {}).get('wavelength_angstrom')} Å；"
        f"K={record.get('configuration', {}).get('k_factor')}",
        f"背景：{background.get('mode', 'none')}；检测平滑：{quality.get('smoothing_points', 1)} 点",
        f"峰形拟合：{'开启' if quality.get('fit_peaks') else '关闭'}；"
        f"收敛 {quality.get('fit_converged_count', 0)}/{len(peaks)}",
        f"仪器展宽：{instrument.get('mode', 'none')}"
        + (f"（常数 {instrument.get('fwhm_deg')}°）" if instrument.get("mode") == "constant" else ""),
        f"检测峰：{len(peaks)} 个",
        f"状态：{record.get('status')}；验证：{record.get('validation_status')}",
    ]
    for peak in peaks[:20]:
        lines.append(
            f"  2θ={peak.get('center_deg', peak['two_theta_deg']):.4g}°  "
            f"I={peak['relative_intensity_pct']:.3g}%  FWHM={_fmt(peak.get('fwhm_deg'))}°  "
            f"拟合FWHM={_fmt_fit(peak.get('fwhm_fit_deg'))}°  η={_fmt_fit(peak.get('eta'))}  "
            f"R²={_fmt_fit(peak.get('fit_r_squared'))}  d={_fmt(peak.get('d_angstrom'))} Å  "
            f"D={_fmt(peak.get('crystallite_size_nm'))} nm")
    if len(peaks) > 20:
        lines.append(f"  仅显示前 20 个峰；完整 {len(peaks)} 个见 xrd_peaks.csv。")
    matching = metrics.get("reference_matching") or []
    if matching:
        lines += ["", "参考相匹配（筛查，不是物相鉴定）："]
        for phase in matching:
            lines.append(f"  {phase['phase']}：{phase['score']:.3f}（{phase['matched_count']}/"
                         f"{phase['reference_count']}）")
    combinations = metrics.get("phase_combinations") or []
    if combinations:
        lines += ["", "多相候选组合（按实测峰覆盖度，仅筛查）："]
        for combo in combinations:
            names = " + ".join(combo["phases"])
            lines.append(f"  {names}：覆盖 {combo['matched_observed_count']}/{combo['observed_count']} 峰，"
                         f"权重 {combo['observed_coverage']:.1%}")
    warnings = list(record.get("warnings") or [])
    if warnings:
        lines += ["", "警告：", *warnings]
    lines += ["", "[COMMON] Pseudo-Voigt 拟合 R²<0.8 时保留半高插值；仪器展宽按 Gaussian 平方差校正；"
                  "未校正时 Scherrer 尺寸为表观尺寸。",
              "背景扣除、平滑与参考匹配是显式选项；原始强度未平滑、排序、裁剪或补值。"]
    return "\n".join(lines)


def _fmt(value):
    return "不可计算" if value is None else f"{float(value):.6g}"
