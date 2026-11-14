"""VSM / XRD / S 参数的目录批量分析页面。"""

from pathlib import Path

from core.vsm_service import VSMConfig
from core.xrd import inspect_xrd_table
from core.xrd_service import XRDConfig
from gui.controllers.sparameter_controller import analyze_s_request
from gui.controllers.vsm_controller import analyze_vsm_request
from gui.controllers.xrd_controller import analyze_xrd_request
from gui.pages.folder_batch_page import FolderBatchPage


def _analyze_vsm(path, name, output, progress, cancelled, dpi):
    config = VSMConfig(path=Path(path), name=name, output=output,
                       mass_from_header=Path(path).suffix.lower() == ".dat", dpi=dpi)
    return analyze_vsm_request(config, progress=progress, cancelled=cancelled)


def _analyze_xrd(path, name, output, progress, cancelled, dpi):
    preview = inspect_xrd_table(path)
    wavelength = preview["metadata"].get("wavelength_angstrom") or 1.5406
    config = XRDConfig(path=Path(path), name=name, output=output,
                       wavelength_angstrom=float(wavelength), dpi=dpi)
    return analyze_xrd_request(config, progress=progress, cancelled=cancelled)


def _analyze_s(path, name, output, progress, cancelled, dpi):
    return analyze_s_request(path, name, output, "", progress, cancelled, dpi=dpi)


def _vsm_row(result):
    record, metrics = result["record"], result.get("metrics") or {}
    return [record.get("sample"), metrics.get("Hc_oe"), metrics.get("Mr"), metrics.get("Ms"),
            metrics.get("squareness"), record.get("status")]


def _xrd_row(result):
    record, metrics = result["record"], result.get("metrics") or {}
    peaks = sorted(metrics.get("peaks") or [], key=lambda item: item.get("relative_intensity_pct", 0),
                   reverse=True)
    main = peaks[0] if peaks else {}
    return [record.get("sample"), len(peaks), main.get("center_deg", main.get("two_theta_deg")),
            main.get("d_angstrom"), record.get("status")]


def _s_row(result):
    record, table = result["record"], result["table"]
    return [record.get("sample"), table["S11_db"].min(), table["S21_db"].min(),
            record.get("schema_status"), record.get("status")]


class VsmBatchPage(FolderBatchPage):
    def __init__(self):
        super().__init__("VSM 批量分析", "vsm_hysteresis", (".csv", ".xlsx", ".xls", ".txt", ".dat"),
                         _analyze_vsm, ["样品", "Hc (Oe)", "Mr", "Ms", "Mr/Ms", "状态"], _vsm_row)


class XrdBatchPage(FolderBatchPage):
    def __init__(self):
        super().__init__("XRD 批量分析", "xrd_peaks", (".csv", ".txt", ".xy", ".dat", ".raw"),
                         _analyze_xrd, ["样品", "峰数", "主峰 2θ (°)", "d (Å)", "状态"], _xrd_row)


class SparamBatchPage(FolderBatchPage):
    def __init__(self):
        super().__init__("S 参数批量分析", "s_parameters", (".sdat",),
                         _analyze_s, ["样品", "min S11 (dB)", "min S21 (dB)", "schema", "状态"], _s_row)
