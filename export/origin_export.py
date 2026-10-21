"""将图中实际数据导出为 Origin 可导入 CSV；不计算任何科学指标。"""
import hashlib
import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.collections import PathCollection


@contextmanager
def recovery_staging(parent):
    """事务未完成时保留备份；包括回滚失败和进程意外结束。"""
    folder = Path(tempfile.mkdtemp(dir=parent, prefix=".f-"))
    try:
        yield folder
    finally:
        if not (folder / "RECOVERY.json").exists():
            shutil.rmtree(folder)


def replace_path(source, target):
    """短暂 Windows 文件占用可重试；永久权限错误有界失败，不跳过输出。"""
    for attempt in range(6):
        try:
            os.replace(source, target)
            return
        except PermissionError as error:
            if getattr(error, "winerror", None) not in {5, 32, 33} or attempt == 5:
                raise
            time.sleep(.05 * 2**attempt)


def attach_grid(ax, x, y, z, z_name):
    """绘图入口附上原网格，不能从等高线轮廓反推或降采样曲面。"""
    ax._origin_grid = (np.asarray(x), np.asarray(y), np.asarray(z), z_name)


def datasets(figure):
    """每条独立曲线保留自己的采样点，参考线单独标记。"""
    for index, ax in enumerate(figure.axes, 1):
        if ax.get_label() == "<colorbar>":
            continue
        info = dict(axes=index, x_label=ax.get_xlabel(), y_label=ax.get_ylabel(), title=ax.get_title())
        if hasattr(ax, "_origin_grid"):
            x, y, z, name = ax._origin_grid
            if z.shape != (len(y), len(x)):
                raise ValueError("图片网格尺寸与坐标不一致。")
            yield dict(info, kind="grid", label=name, z_label=name), pd.DataFrame({
                "X": np.tile(x, len(y)), "Y": np.repeat(y, len(x)), "Z": z.reshape(-1)})
        for i, line in enumerate(ax.lines, 1):
            if not line.get_visible():
                continue
            x = np.ma.asarray(line.get_xdata(), dtype=float).filled(np.nan)
            y = np.ma.asarray(line.get_ydata(), dtype=float).filled(np.nan)
            kind = "curve"
            if line.get_transform() == ax.get_yaxis_transform():
                x = np.asarray(ax.get_xlim()); kind = "horizontal_reference"
            elif line.get_transform() == ax.get_xaxis_transform():
                y = np.asarray(ax.get_ylim()); kind = "vertical_reference"
            label = line.get_label()
            yield dict(info, kind=kind, label=label if not label.startswith("_") else f"curve_{i}"), pd.DataFrame({"X":x,"Y":y})
        for collection in ax.collections:
            if isinstance(collection, PathCollection) and collection.get_visible() and collection.get_offset_transform() == ax.transData:
                xy = np.ma.asarray(collection.get_offsets(), dtype=float).filled(np.nan)
                yield dict(info, kind="scatter", label=collection.get_label()), pd.DataFrame({"X":xy[:,0],"Y":xy[:,1]})
        # 显示带是装饰/参考范围，不冒充原始测量点；完整参数写入说明。
        for patch in ax.patches:
            if hasattr(patch, "get_y") and patch.get_label() == "|z| display band":
                yield dict(info, kind="reference_band", label=patch.get_label()), pd.DataFrame({
                    "Y_lower":[patch.get_y()], "Y_upper":[patch.get_y()+patch.get_height()]})


_DATA_LINKS = {}


def _digest_file(path):
    value = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _deduplicate(path, digest):
    """同一卷上内容相同的导出数据用硬链接复用，减少多图重复网格占用。

    失败（跨卷、文件系统不支持）时保留独立副本，不改变任何数据内容。
    """
    device = os.stat(path.parent).st_dev
    existing = _DATA_LINKS.get((device, digest))
    if existing is None or not existing.is_file():
        return
    temporary = path.with_name(path.name + ".link")
    try:
        os.link(existing, temporary)
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)


def save_figure_bundle(figure, path, *, cancelled=lambda:False, cancel_error=InterruptedError,
                       provenance=None, **save_options):
    """图片与数据目录一起替换；失败/取消回滚旧输出，防止只更新一半。

    provenance 记录运行来源与验证状态；独立导出没有上下文时由调用方省略，
    metadata 中明确写 validation_status=unknown。
    """
    path = Path(path)
    companion = path.with_name(path.name + ".data")
    def checkpoint():
        if cancelled():
            raise cancel_error("图片和配套数据导出已取消；旧文件未改变。")
    checkpoint()
    if path.exists() and not path.is_file():
        raise ValueError("图片目标不能是目录。")
    if companion.is_symlink() or path.is_symlink():
        raise ValueError("拒绝覆盖符号链接输出。")
    if companion.exists():
        if not companion.is_dir():
            raise ValueError(f"配套数据路径已被同名文件占用：{companion}")
        marker = companion/"metadata.json"
        if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")).get("format") != "origin_csv_bundle_v1":
            raise ValueError(f"配套目录已存在且不是软件生成的数据目录：{companion}")
    if provenance is None:
        from export.provenance import figure_provenance
        provenance = figure_provenance(dpi=save_options.get("dpi"))
    with recovery_staging(path.parent) as temporary:
        staging = Path(temporary)
        staged_image = staging/ ("image"+path.suffix)
        staged_data = staging/"data"
        staged_data.mkdir()
        figure.savefig(staged_image, **save_options)
        manifest = {"format":"origin_csv_bundle_v1", "image":path.name,
                    "figure_title":figure._suptitle.get_text() if figure._suptitle else "",
                    "encoding":"UTF-8 BOM", "delimiter":",", "missing":"NaN", "interpolation":"OFF",
                    "provenance": provenance, "datasets":[]}
        digests = {}
        for number, (info, table) in enumerate(datasets(figure), 1):
            checkpoint()
            name = f"{number:02d}.csv"
            staged = staged_data/name
            table.to_csv(staged,index=False,encoding="utf-8-sig",float_format="%.17g",na_rep="NaN")
            digests[name] = _digest_file(staged)
            _deduplicate(staged, digests[name])
            manifest["datasets"].append(dict(info,file=name,rows=len(table),columns=list(table.columns)))
        if not manifest["datasets"]:
            raise ValueError("图片没有可导出的数据；未写入不完整的图片输出。")
        (staged_data/"metadata.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
        (staged_data/"provenance.json").write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding="utf-8")
        lines = ["Origin import: Data > Import From File > CSV / Single ASCII (menu varies by version).",
                 "Encoding UTF-8; delimiter comma; first row column names. Set X/Y or X/Y/Z column roles.",
                 "Each CSV is an independent series/grid. No resampling. NaN means undefined; inf/-inf are retained.",
                 "Grid rows: Y (thickness) outer loop, X (frequency) inner loop; original full grid, not contour vertices.",
                 "Reference lines/bands are display guides, not measured samples. Labels and units follow the figure.",
                 f"Provenance: run_id={provenance.get('run_id') or 'unknown'}; "
                 f"validation_status={provenance.get('validation_status') or 'unknown'}; "
                 f"software_version={provenance.get('software_version')}.", ""]
        for entry in manifest["datasets"]:
            lines.append(f"{entry['file']}: {entry['label']} | X: {entry['x_label']} | Y: {entry['y_label']} | Z: {entry.get('z_label','')} | rows: {entry['rows']}")
        (staged_data/"README.txt").write_text("\n".join(lines),encoding="utf-8-sig")
        index = pd.DataFrame(manifest["datasets"]).drop(columns=["columns"])
        index.insert(0, "run_id", provenance.get("run_id") or "")
        index.insert(1, "validation_status", provenance.get("validation_status") or "unknown")
        index.to_csv(staged_data/"index.csv", index=False, encoding="utf-8-sig")
        checkpoint()
        old_image, old_data = staging/"old_image", staging/"old_data"
        moved_image = moved_data = installed_image = installed_data = False
        recovery = staging / "RECOVERY.json"
        recovery.write_text(json.dumps({"image":str(path.resolve()), "data":str(companion.resolve()),
            "note":"未完成的导出事务。old_image / old_data 是旧输出备份；请勿删除本目录。"},
            ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            if path.exists():
                replace_path(path,old_image); moved_image=True
            if companion.exists():
                replace_path(companion,old_data); moved_data=True
            replace_path(staged_data,companion); installed_data=True
            replace_path(staged_image,path); installed_image=True
            device = os.stat(companion).st_dev
            for name, digest in digests.items():
                _DATA_LINKS[(device, digest)] = companion / name
        except Exception as error:
            failures = []
            for needed, source, target in ((installed_image,path,staged_image),
                    (installed_data,companion,staged_data), (moved_image,old_image,path),
                    (moved_data,old_data,companion)):
                if needed:
                    try:
                        replace_path(source,target)
                    except Exception as rollback_error:
                        failures.append(str(rollback_error))
            if failures:
                raise RuntimeError(f"导出失败且恢复未完成。备份保留在：{staging.resolve()}；"
                                   "请保留此目录，按 RECOVERY.json 恢复旧文件。") from error
            recovery.unlink()
            raise
        recovery.unlink()
    return path
