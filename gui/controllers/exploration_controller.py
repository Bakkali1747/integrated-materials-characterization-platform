"""仅复用已完成矩阵和正式 EAB API；不重新计算材料模型。"""
from core.eab import absorption_bands
from core.models import RLResult
from core.rl_calculator import minimum_points


def thickness_snapshot(completed, index):
    result = completed["result"]
    if not 0 <= index < len(result.thickness_mm):
        raise ValueError("厚度索引超出已计算网格。")
    curve = RLResult(result.frequency_ghz, result.thickness_mm[index:index+1],
                     result.rl_db[index:index+1], result.normalized_impedance[index:index+1])
    threshold = completed["record"]["rl_threshold_db"]
    return dict(completed, curve=curve), {
        "thickness_mm":float(curve.thickness_mm[0]), "minima":minimum_points(curve),
        "standard":absorption_bands(curve.frequency_ghz, curve.rl_db[0], -10.),
        "selected":absorption_bands(curve.frequency_ghz, curve.rl_db[0], threshold)}
