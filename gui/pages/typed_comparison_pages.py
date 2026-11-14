"""VSM / XRD / S 参数的多样品比较页面。"""

from gui.controllers.sparameter_controller import load_s_request
from gui.controllers.vsm_controller import load_vsm_request
from gui.controllers.xrd_controller import load_xrd_request
from gui.pages.run_comparison_page import RunComparisonPage
from plotting.type_comparison import plot_sparameter_comparison, plot_vsm_comparison, plot_xrd_comparison


def _vsm_row(run):
    record, metrics = run["record"], run["metrics"]
    return [record.get("sample"), metrics.get("Hc_oe"), metrics.get("Mr"), metrics.get("Ms"),
            metrics.get("squareness"), record.get("status"), record.get("validation_status")]


def _xrd_row(run):
    record, metrics = run["record"], run["metrics"]
    peaks = sorted(metrics.get("peaks") or [], key=lambda item: item.get("relative_intensity_pct", 0),
                   reverse=True)
    main = peaks[0] if peaks else {}
    return [record.get("sample"), len(peaks), main.get("center_deg", main.get("two_theta_deg")),
            main.get("d_angstrom"), main.get("fwhm_deg"), main.get("crystallite_size_nm"),
            record.get("status"), record.get("validation_status")]


def _s_row(run):
    record, table = run["record"], run["table"]
    return [record.get("sample"), table["S11_db"].min(), table["S21_db"].min(),
            record.get("schema_status"), record.get("status")]


def _load_s(directory):
    run = load_s_request(directory)
    run["record"].setdefault("analysis_kind", "s_parameters")
    return run


class VsmComparisonPage(RunComparisonPage):
    def __init__(self):
        super().__init__("VSM 多样品比较", "vsm_hysteresis", load_vsm_request,
                         lambda runs: {"vsm": plot_vsm_comparison(runs)},
                         ["样品", "Hc (Oe)", "Mr", "Ms", "Mr/Ms", "状态", "验证"],
                         _vsm_row, "添加两个以上已完成 VSM 运行")


class XrdComparisonPage(RunComparisonPage):
    def __init__(self):
        super().__init__("XRD 多样品比较", "xrd_peaks", load_xrd_request,
                         lambda runs: {"xrd": plot_xrd_comparison(runs)},
                         ["样品", "峰数", "主峰 2θ (°)", "d (Å)", "FWHM (°)", "Scherrer (nm)",
                          "状态", "验证"],
                         _xrd_row, "添加两个以上已完成 XRD 运行")


class SparamComparisonPage(RunComparisonPage):
    def __init__(self):
        super().__init__("S 参数多样品比较", "s_parameters", _load_s,
                         lambda runs: {"S11": plot_sparameter_comparison(runs, "S11"),
                                       "S21": plot_sparameter_comparison(runs, "S21")},
                         ["样品", "min S11 (dB)", "min S21 (dB)", "schema", "状态"],
                         _s_row, "添加两个以上已完成 S 参数运行")
