"""参考 RL 逐点对照；不计算 RL，不自动授予科研验证状态。"""
import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from core import __version__
from core.parser import decode_text, read_csv_table
from export.provenance import artifact_hashes
from gui.controllers.analysis_controller import Cancelled


def matching_indices(grid, values):
    grid=np.asarray(grid); values=np.asarray(values)
    right=np.clip(np.searchsorted(grid,values),0,len(grid)-1)
    left=np.maximum(right-1,0)
    lr=np.isclose(grid[left],values,rtol=0,atol=1e-9)
    rr=np.isclose(grid[right],values,rtol=0,atol=1e-9)
    if np.any(lr & rr & (left!=right)):
        raise ValueError("参考坐标在 1e-9 匹配容差内对应多个网格点，请使用更明确的坐标。")
    return np.where(rr,right,left), lr|rr


def compare_reference(result, table, tolerance_db):
    required=["frequency_ghz","thickness_mm","rl_db"]
    if not set(required).issubset(table.columns) or table.empty:
        raise ValueError("参考 CSV 需要 frequency_ghz、thickness_mm、rl_db 三列及数据。")
    data=table[required].apply(pd.to_numeric,errors="raise").copy()
    if not np.isfinite(data.to_numpy()).all() or not np.isfinite(tolerance_db) or tolerance_db<0:
        raise ValueError("参考数值与偏差容差必须有限；容差不得为负。")
    if (data[["frequency_ghz","thickness_mm"]]<=0).any().any() or data.duplicated(required[:2]).any():
        raise ValueError("参考坐标须为正且不能重复。")
    fi,fok=matching_indices(result.frequency_ghz,data.frequency_ghz)
    di,dok=matching_indices(result.thickness_mm,data.thickness_mm)
    matched=fok & dok
    actual=np.full(len(data),np.nan)
    actual[matched]=result.rl_db[di[matched],fi[matched]]
    finite=matched & np.isfinite(actual)
    data.rename(columns={"rl_db":"reference_rl_db"},inplace=True)
    data["calculated_rl_db"]=actual
    data["difference_db"]=actual-data.reference_rl_db
    data["absolute_difference_db"]=np.abs(data.difference_db)
    data["status"]=np.where(~matched,"UNMATCHED",np.where(~finite,"NONFINITE",np.where(data.absolute_difference_db<=tolerance_db,"WITHIN_TOLERANCE","OUTSIDE_TOLERANCE")))
    return data


def export_reference_comparison(completed, reference, output, notes, tolerance_db=.05, cancelled=lambda:False):
    source=completed["directory"].resolve(); output=Path(output).resolve(); reference=Path(reference)
    if output.is_relative_to(source): raise ValueError("对照报告请保存到原分析目录以外，避免改变追溯快照。")
    if not notes.strip(): raise ValueError("请记录参考软件版本、样品、厚度和模型条件；尚未确认的项目请明确写明。")
    if cancelled(): raise Cancelled("参考对照已取消")
    raw=reference.read_bytes(); text,_=decode_text(raw); table,_=read_csv_table(text,",")
    compared=compare_reference(completed["result"],table,tolerance_db)
    if cancelled(): raise Cancelled("参考对照已取消")
    directory=output/("reference_"+datetime.now().strftime("%Y%m%dT%H%M%S")+"_"+uuid.uuid4().hex[:8])
    directory.mkdir(parents=True)
    record={"software_version":__version__,"analysis_date":datetime.now().astimezone().isoformat(),
        "status":"started","validation_status":"pending","source_run":str(source),
        "source_record_sha256":hashlib.sha256((source/"analysis_record.json").read_bytes()).hexdigest(),
        "raw_sha256":completed["record"].get("raw_sha256"),
        "reference_file":str(reference.resolve()),"reference_sha256":hashlib.sha256(raw).hexdigest(),
        "notes":notes,"absolute_tolerance_db":tolerance_db,"coordinate_tolerance":1e-9,
        "interpolation":"OFF","counts":compared.status.value_counts().to_dict(),
        "scope":"Calculated metal-backed RL only; not measured S11 or manufacturer schema validation"}
    try:
        (directory/"reference_source.csv").write_bytes(raw)
        from export.csv_safety import escape_formula_cells
        escape_formula_cells(compared).to_csv(directory/"point_comparison.csv",index=False,encoding="utf-8-sig",float_format="%.17g")
        record["status"]="success"
    except Exception as error:
        record.update(status="failed",error=str(error)); raise
    finally:
        record["artifacts_sha256"]=artifact_hashes(directory)
        (directory/"reference_record.json").write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
    return directory
