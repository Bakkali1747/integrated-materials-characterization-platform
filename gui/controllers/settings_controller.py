"""GUI 偏好配置；独立于科研核心配置，严格校验并原子保存。"""
from pathlib import Path
import json
import math
import logging
import os
import tempfile
from application_paths import user_data_root


def defaults():
    return dict(version=1, frequency_unit="GHz", thickness_min=1., thickness_max=5.,
                thickness_step=.01, curve_thickness=2., threshold=-10.,
                output=str(user_data_root()/"output"), dpi=600, figure_format="png", interpolation="OFF")


def validate_settings(values):
    result = defaults()
    if not isinstance(values, dict) or set(values)-set(result):
        raise ValueError("设置格式不正确，或含有未知字段。")
    result.update(values)
    if type(result["version"]) is not int or result["version"] != 1:
        raise ValueError("不支持此设置文件版本。")
    if result["frequency_unit"] not in {"GHz", "MHz", "kHz", "Hz"}:
        raise ValueError("频率单位必须为 GHz / MHz / kHz / Hz。")
    for key in ("thickness_min", "thickness_max", "thickness_step", "curve_thickness", "threshold"):
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value):
            raise ValueError(f"{key} 必须为有限数值。")
        if key != "threshold" and not .0001 <= value <= 1000:
            raise ValueError("厚度参数必须在 0.0001–1000 mm 内。")
    if result["thickness_min"] > result["thickness_max"]:
        raise ValueError("厚度下限不能大于上限。")
    if not -1000 <= result["threshold"] <= 0:
        raise ValueError("RL 阈值必须在 −1000–0 dB 内。")
    if type(result["dpi"]) is not int or not 72 <= result["dpi"] <= 1200:
        raise ValueError("DPI 必须是 72–1200 的整数。")
    if result["figure_format"] not in {"png", "tiff", "pdf", "svg"}:
        raise ValueError("图片格式必须为 PNG / TIFF / PDF / SVG。")
    if result["interpolation"] != "OFF":
        raise ValueError("当前版本缺失数据插值仅支持 OFF。")
    if not isinstance(result["output"], str) or not result["output"].strip():
        raise ValueError("请选择输出目录。")
    output = Path(result["output"]).expanduser()
    if not output.is_absolute() or (output.exists() and not output.is_dir()):
        raise ValueError("输出目录必须是绝对目录路径，不能是文件。")
    result["output"] = str(output.resolve())
    return result


class SettingsStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else user_data_root()/"settings/gui.json"

    def load(self):
        if not self.path.exists():
            return defaults(), ""
        try:
            return validate_settings(json.loads(self.path.read_text(encoding="utf-8"))), ""
        except (OSError, ValueError, TypeError) as error:
            logging.getLogger("microwave.gui").exception("设置读取失败：%s", self.path)
            return defaults(), f"设置读取失败，已使用默认值；原文件保留。{error}"

    def save(self, values):
        result = validate_settings(values)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
            os.replace(temporary, self.path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        return result
