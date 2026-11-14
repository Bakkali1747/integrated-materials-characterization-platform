"""展示正式严格 parser 的检查证据，不重复实现验证算法。"""


def quality_rows(record):
    kind = record.get("analysis_kind")
    if kind in {"vsm_hysteresis", "xrd_peaks", "s_parameters"}:
        rows = [("Analysis kind", "PASS", str(kind)),
                ("Run status", "PASS" if record.get("status") in {"success", "not_computable"} else "WARNING",
                 str(record.get("status", "unknown"))),
                ("Validation", "PENDING", str(record.get("validation_status", "pending")))]
        if record.get("error"):
            rows.append(("Analysis", "FAIL" if record.get("status") == "failed" else "WARNING",
                         record["error"]))
        for warning in record.get("warnings", []):
            rows.append(("Data warning", "WARNING", str(warning)))
        return rows
    parsed = bool(record.get("source", {}).get("parser")) and bool(record.get("frequency_points"))
    state = "PASS" if parsed else "PENDING"
    evidence = "正式严格 parser 已通过" if parsed else "未取得完整解析证据"
    rows = [(name, state, evidence) for name in
            ("Frequency monotonic", "Missing values", "NaN / infinite", "Duplicate frequencies")]
    rows += [("Complex convention", "PENDING", "虚部定义 / 测量约定需外部确认"),
             ("Parser validation", "PENDING", record.get("schema_status", record.get("validation_status", "pending")))]
    if record.get("error"):
        rows.append(("Analysis", "FAIL" if record.get("status") == "failed" else "WARNING", record["error"]))
    for warning in record.get("warnings", []):
        rows.append(("Data warning", "WARNING", str(warning)))
    qc = record.get("quality_checks", {})
    for key in ("magnitude_violation_counts", "energy_violation_count", "negative_absorption_count"):
        if key in qc:
            value = qc[key]
            violation = any(value.values()) if isinstance(value, dict) else bool(value)
            rows.append((key, "WARNING" if violation else "PASS", str(value)))
    if "reciprocity" in qc:
        value = qc["reciprocity"]
        rows.append(("Reciprocity", "WARNING" if value.get("violation_count") else "PASS", str(value)))
    return rows


def quality_text(record):
    return "Quality Control\n" + "\n".join(f"{name}: {state} — {note}" for name, state, note in quality_rows(record))
