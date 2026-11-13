"""把已完成的单样品分析运行登记为工作区 AnalysisRun。

本模块只读取分析记录与已保存产物，不重新计算、不修改数值结果；验证状态也不会
因为登记动作而升级为 VALIDATED。
"""

from pathlib import Path
from typing import Any

from core.common.measurement import MeasurementType
from core.common.validation_status import ValidationStatus

ELECTROMAGNETIC_ANALYSIS_TYPE = "electromagnetic_rl"
S_PARAMETER_ANALYSIS_TYPE = "s_parameters"
ANALYSIS_TYPE_LABELS = {ELECTROMAGNETIC_ANALYSIS_TYPE: "电磁 RL 分析",
                        S_PARAMETER_ANALYSIS_TYPE: "S 参数分析"}
RESULT_ARTIFACTS = {
    ELECTROMAGNETIC_ANALYSIS_TYPE: ("summary.json", "analysis_record.json", "thickness_summary.csv",
                                    "RL_matrix.csv", "RL_curve.csv", "electromagnetic_parameters.csv",
                                    "parsed_data.csv"),
    S_PARAMETER_ANALYSIS_TYPE: ("analysis_record.json", "sparameters_by_frequency.csv", "quality_checks.json",
                                "metadata.xml", "sparameters_complex.npz", "raw_numeric_columns.csv"),
}
PLOT_SUFFIXES = {".png", ".tif", ".tiff", ".pdf", ".svg", ".eps"}


def analysis_type_label(value: str) -> str:
    """工作区显示名；未知类型原样显示，不伪造已知语义。"""
    return ANALYSIS_TYPE_LABELS.get(str(value), str(value))


def analysis_run_status(record: dict[str, Any], warnings: list[str] | None = None) -> ValidationStatus:
    """成功且无警告记 PENDING，有警告记 WARNING；绝不产生 VALIDATED。

    非成功记录直接拒绝：失败或取消的运行没有可复核的完整数值产物，不应作为
    该测试的有效分析历史。
    """
    status = str(record.get("status", "")).strip().lower()
    if status != "success":
        raise ValueError("只有成功完成的分析运行才能登记到样品工作区。")
    values = record_warnings(record) if warnings is None else warnings
    return ValidationStatus.WARNING if values else ValidationStatus.PENDING


def record_warnings(record: dict[str, Any]) -> list[str]:
    """合并顶层警告与 QC 警告；S 参数将逐点筛查警告保存在 quality_checks 中。"""
    values = [str(item).strip() for item in record.get("warnings") or [] if str(item).strip()]
    quality = record.get("quality_checks")
    if isinstance(quality, dict):
        values += [str(item).strip() for item in quality.get("warnings") or [] if str(item).strip()]
    return list(dict.fromkeys(values))


def _analysis_parameters(record: dict[str, Any], analysis_type: str) -> dict[str, Any]:
    """保存能复现该分析的参数；S 参数记录没有 configuration，保存映射与容差。"""
    if analysis_type == S_PARAMETER_ANALYSIS_TYPE:
        parameters = {"mapping": dict(record.get("mapping") or {}),
                      "tolerances": dict(record.get("tolerances") or {}),
                      "schema_status": record.get("schema_status"),
                      "schema_id": (record.get("mapping") or {}).get("schema_id")}
        if record.get("schema_file"):
            parameters["schema_file"] = record["schema_file"]
            parameters["schema_file_sha256"] = record.get("schema_file_sha256")
        return parameters
    return dict(record.get("configuration") or {})


def analysis_run_fields(directory: str | Path, record: dict[str, Any],
                        *, analysis_type: str = ELECTROMAGNETIC_ANALYSIS_TYPE) -> dict[str, Any]:
    """输入完成运行目录与记录；返回 add_analysis_run 所需字段。

    引用统一保存绝对路径：结果目录、数值产物、已保存图片，便于后续打开与核验。
    """
    folder = Path(directory).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError(f"分析运行目录不存在：{folder}")
    warnings = record_warnings(record)
    validation_status = analysis_run_status(record, warnings)
    software = str(record.get("software_version") or "").strip() or "unknown"
    cache = record.get("analysis_cache_version")
    if cache is None:
        cache = (record.get("source") or {}).get("parser") or "sdat-v1"
    result_refs = [str(folder)]
    for name in RESULT_ARTIFACTS.get(analysis_type, ("analysis_record.json",)):
        path = folder / name
        if path.is_file():
            result_refs.append(str(path))
    figures = folder / "figures"
    plot_refs = sorted(str(path.resolve()) for path in figures.glob("*")
                       if path.is_file() and path.suffix.lower() in PLOT_SUFFIXES) if figures.is_dir() else []
    return {
        "analysis_type": analysis_type,
        "analysis_engine_version": f"{software}/{cache}",
        "parameters": _analysis_parameters(record, analysis_type),
        "git_commit": str((record.get("git") or {}).get("commit") or "unavailable"),
        "validation_status": validation_status,
        "warnings": warnings,
        "errors": [],
        "result_refs": result_refs,
        "plot_refs": plot_refs,
        "export_refs": [],
    }


def _measurement_digest(measurement, raw_file: str) -> str | None:
    """按解析后的路径查找测试登记哈希，避免相对路径与大小写差异误判。"""
    target = Path(raw_file).resolve()
    for name, digest in measurement.source_sha256.items():
        if Path(name).expanduser().resolve() == target:
            return str(digest)
    return None


def link_measurement_run(repository, project_id: str, sample_id: str, measurement_id: str,
                         directory: str | Path, record: dict[str, Any], *,
                         analysis_type: str,
                         measurement_type: MeasurementType = MeasurementType.ELECTROMAGNETIC):
    """登记一次完成的测试分析，并把测试状态更新为运行结论。

    校验顺序：测试类型 → 原始文件归属 → 源文件 SHA-256 → 运行状态与产物。
    任何一步不满足都抛 ValueError，且不写入运行、不修改测试状态。
    """
    measurement = repository.get_measurement(project_id, sample_id, measurement_id)
    actual_type = MeasurementType.coerce(measurement.measurement_type)
    if actual_type is not measurement_type:
        raise ValueError(f"只有 {measurement_type.label} 测试可以登记该分析运行。")
    raw_file = str(record.get("raw_file") or "").strip()
    if not raw_file:
        raise ValueError("分析运行缺少原始文件路径，无法与测试关联。")
    expected = _measurement_digest(measurement, raw_file)
    if expected is None:
        raise ValueError("分析使用的原始文件不属于该测试，未登记运行。")
    actual = str(record.get("raw_sha256") or "").strip()
    if not actual or actual.lower() != expected.lower():
        raise ValueError("分析运行时原始文件 SHA-256 与测试登记不一致，请重新核验来源后再登记。")
    fields = analysis_run_fields(directory, record, analysis_type=analysis_type)
    run = repository.add_analysis_run(project_id, sample_id, measurement_id, **fields)
    repository.set_measurement_validation(project_id, sample_id, measurement_id, fields["validation_status"])
    return run


def link_electromagnetic_run(repository, project_id: str, sample_id: str, measurement_id: str,
                             directory: str | Path, record: dict[str, Any]):
    """登记电磁 ε/μ RL 分析运行。"""
    return link_measurement_run(repository, project_id, sample_id, measurement_id, directory, record,
                                analysis_type=ELECTROMAGNETIC_ANALYSIS_TYPE)


def link_sparameter_run(repository, project_id: str, sample_id: str, measurement_id: str,
                        directory: str | Path, record: dict[str, Any]):
    """登记实测 S 参数分析运行；候选映射状态不会因此升级。"""
    return link_measurement_run(repository, project_id, sample_id, measurement_id, directory, record,
                                analysis_type=S_PARAMETER_ANALYSIS_TYPE)
