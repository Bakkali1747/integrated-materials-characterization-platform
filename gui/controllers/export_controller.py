"""图片导出适配；使用已完成的核心结果，不接触 Qt Canvas。"""

from pathlib import Path
import os
import tempfile
from plotting.em_parameters import plot_parameters
from plotting.rl_plot import plot_rl_curve, plot_rl_2d
from plotting.style import PlotStyle, plt
from gui.controllers.analysis_controller import Cancelled
from gui.controllers.science_figures import make_figure


def export_all_builders(builders, source, output, extension, dpi, progress, cancelled):
    """新建独立导出目录；逐图原子保存，取消保留已完成产物及记录。"""
    import json
    import uuid
    import hashlib
    from core import __version__
    from datetime import datetime
    from export.provenance import artifact_hashes
    if extension not in {"png", "tiff", "pdf", "svg"} or not builders:
        raise ValueError("请选择有效图片格式和已完成的图组。")
    output, source = Path(output).resolve(), Path(source).resolve()
    if output.is_relative_to(source):
        raise ValueError("请选择分析目录以外的导出位置，保留原追溯产物。")
    directory = output / ("figures_"+datetime.now().strftime("%Y%m%dT%H%M%S")+"_"+uuid.uuid4().hex[:8])
    directory.mkdir(parents=True)
    record = dict(status="started", software_version=__version__, analysis_date=datetime.now().astimezone().isoformat(),
                  source_run=str(source), source_records_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*_record.json")},
                  dpi=dpi, figure_format=extension, completed=[])
    try:
        for key, builder in builders.items():
            if cancelled():
                raise Cancelled("全部图片导出已取消；已保存图片保留。")
            if Path(key).name != key or key in {".", ".."}:
                raise ValueError("无效图片名称。")
            figure, temporary = None, None
            try:
                figure = builder()
                with tempfile.NamedTemporaryFile(dir=directory, suffix="."+extension, delete=False) as handle:
                    temporary = Path(handle.name)
                figure.savefig(temporary, dpi=dpi, bbox_inches="tight")
                if cancelled():
                    raise Cancelled("全部图片导出已取消；已保存图片保留。")
                target = directory / f"{key}.{extension}"
                os.replace(temporary, target)
                record["completed"].append(target.name)
                progress(int(len(record["completed"])*100/len(builders)), "导出 "+key)
            finally:
                if figure is not None:
                    plt.close(figure)
                if temporary:
                    temporary.unlink(missing_ok=True)
        record["status"] = "success"
        return directory
    except Exception as error:
        record.update(status="cancelled" if isinstance(error,Cancelled) else "failed", error=str(error))
        raise
    finally:
        record["artifacts_sha256"] = artifact_hashes(directory)
        (directory/"export_record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def export_figure(completed, key, path, progress, cancelled, dpi=600):
    """输入已完成结果与图类型；复用绘图 API，原子替换目标图片。"""
    path = Path(path)
    if path.suffix.lower() not in {".png", ".tiff", ".tif", ".pdf", ".svg"}:
        raise ValueError("图片格式不支持。")
    if path.resolve().is_relative_to(completed["directory"].resolve()):
        raise ValueError("不能覆盖已有分析追溯目录。")
    if cancelled():
        raise Cancelled("图片导出已取消。")
    style = PlotStyle(dpi=dpi)
    figure = make_figure(completed, key, style)
    temporary = None
    try:
        figure.suptitle("PENDING VALIDATION", fontsize=10, color="0.4")
        progress(20, "保存图片…")
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=path.suffix, delete=False) as handle:
            temporary = Path(handle.name)
        figure.savefig(temporary, dpi=dpi)
        if cancelled():
            raise Cancelled("图片导出已取消；原目标未改变。")
        os.replace(temporary, path)
        progress(100, "图片保存完成")
        return path
    finally:
        plt.close(figure)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
