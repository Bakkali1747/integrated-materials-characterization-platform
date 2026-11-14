"""COD 无机物相库：本地 SQLite search-match，仅做候选相筛查。"""

from __future__ import annotations

import math
import sqlite3
import zipfile
from pathlib import Path

from application_paths import resource_root, user_data_root

ARCHIVE_NAME = "cod_inorg_compact.zip"
LIBRARY_NAME = "cod_inorg_compact.sqlite"
LIBRARY_TITLE = "COD 无机物相库"
LIBRARY_LICENSE = "CC-BY-4.0（COD / QualX COD-inorganic）"


def library_directory():
    return user_data_root() / "phase_library"


def library_path():
    return library_directory() / LIBRARY_NAME


def ensure_library(progress=None):
    """返回可用的 COD 库；首次运行时从安装包内压缩库解压到用户数据目录。"""
    target = library_path()
    if target.is_file() and target.stat().st_size > 1_000_000:
        return target
    source = Path("output") / "phase-library" / LIBRARY_NAME
    if source.is_file():
        return source
    archive = resource_root() / "assets" / ARCHIVE_NAME
    if not archive.is_file():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    if progress:
        progress(5, "解压 COD 物相库")
    with zipfile.ZipFile(archive) as handle:
        with handle.open(LIBRARY_NAME) as reader, temporary.open("wb") as writer:
            while block := reader.read(1024 * 1024):
                writer.write(block)
    temporary.replace(target)
    if progress:
        progress(100, "COD 物相库已就绪")
    return target


def _two_theta_to_d(two_theta_deg, wavelength_angstrom):
    theta = math.radians(two_theta_deg / 2.0)
    sine = math.sin(theta)
    return wavelength_angstrom / (2.0 * sine) if sine > 0 else None


def _d_to_two_theta(d_angstrom, wavelength_angstrom):
    sine = wavelength_angstrom / (2.0 * d_angstrom)
    if not 0 < sine <= 1:
        return None
    return math.degrees(2.0 * math.asin(sine))


class PhaseLibrary:
    """只读物相库；对每次 XRD 分析返回按覆盖度排序的候选相。"""

    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"物相库不存在：{self.path}")
        self.connection = sqlite3.connect(str(self.path))
        self.connection.execute("PRAGMA query_only=ON")
        tables = {row[0] for row in self.connection.execute(
            "select name from sqlite_master where type='table'")}
        if not {"phases", "lines"}.issubset(tables):
            raise ValueError("物相库缺少 phases/lines 表。")

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def meta(self):
        return {key: value for key, value in self.connection.execute("select key,value from meta")}

    def count(self):
        return int(self.connection.execute("select count(*) from phases").fetchone()[0])

    def search(self, peaks, wavelength_angstrom, *, tolerance_deg=0.2, top_n=10,
               max_candidates=3000, minimum_relative=5.0):
        """用 2θ 容差匹配 COD 的 d 列表；分数由参考覆盖与实测覆盖加权。"""
        observed = []
        for peak in peaks:
            relative = float(peak.get("relative_intensity_pct", 0.0))
            if relative < minimum_relative:
                continue
            angle = peak.get("center_deg", peak.get("two_theta_deg"))
            if angle is None:
                continue
            d_value = peak.get("d_angstrom") or _two_theta_to_d(float(angle), wavelength_angstrom)
            if d_value is None:
                continue
            observed.append({"two_theta": float(angle), "d": float(d_value), "relative": relative})
        if not observed:
            return []
        observed.sort(key=lambda item: item["relative"], reverse=True)
        observed = observed[:8]
        observed_weight = sum(item["relative"] for item in observed) or 1.0

        counts = {}
        for item in observed:
            low = max(0.01, item["two_theta"] - tolerance_deg)
            high = min(179.99, item["two_theta"] + tolerance_deg)
            d_high = _two_theta_to_d(low, wavelength_angstrom)
            d_low = _two_theta_to_d(high, wavelength_angstrom)
            if d_low is None or d_high is None or d_low >= d_high:
                continue
            for phase_id, in self.connection.execute(
                    "select distinct phase_id from lines where d between ? and ?", (d_low, d_high)):
                counts[phase_id] = counts.get(phase_id, 0) + 1
        if not counts:
            return []
        candidates = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)[:max_candidates]
        phase_ids = [phase_id for phase_id, _ in candidates]
        phase_rows = {}
        line_rows = {phase_id: [] for phase_id in phase_ids}
        for start in range(0, len(phase_ids), 500):
            chunk = phase_ids[start:start + 500]
            placeholders = ",".join("?" for _ in chunk)
            for row in self.connection.execute(
                    f"select id,formula,mineral,spacegroup,quality,rir from phases where id in ({placeholders})",
                    chunk):
                phase_rows[row[0]] = row[1:]
            for phase_id, d_value, intensity in self.connection.execute(
                    f"select phase_id,d,intensity from lines where phase_id in ({placeholders})", chunk):
                line_rows[phase_id].append((float(d_value), float(intensity)))

        results = []
        for phase_id in phase_ids:
            lines = sorted(line_rows.get(phase_id, []), key=lambda item: item[1], reverse=True)
            if not lines:
                continue
            total_ref = sum(intensity for _, intensity in lines) or 1.0
            used = set()
            matched_weight = 0.0
            matched_weight_observed = 0.0
            matched_lines = []
            for d_value, intensity in lines:
                angle = _d_to_two_theta(d_value, wavelength_angstrom)
                if angle is None:
                    continue
                best = None
                for index, item in enumerate(observed):
                    if index in used:
                        continue
                    delta = abs(item["two_theta"] - angle)
                    if delta <= tolerance_deg and (best is None or delta < best[0]):
                        best = (delta, index)
                if best is None:
                    continue
                delta, index = best
                used.add(index)
                matched_weight += intensity
                matched_weight_observed += observed[index]["relative"]
                matched_lines.append({
                    "reference_two_theta_deg": angle,
                    "reference_d_angstrom": d_value,
                    "observed_two_theta_deg": observed[index]["two_theta"],
                    "delta_deg": float(observed[index]["two_theta"] - angle),
                    "reference_relative_intensity": intensity,
                    "observed_relative_intensity": observed[index]["relative"],
                })
            if not matched_lines:
                continue
            reference_coverage = matched_weight / total_ref
            observed_coverage = matched_weight_observed / observed_weight
            score = 0.6 * reference_coverage + 0.4 * observed_coverage
            formula, mineral, spacegroup, quality, rir = phase_rows.get(
                phase_id, (None, None, None, None, None))
            results.append({
                "phase_id": int(phase_id), "formula": formula, "mineral": mineral,
                "spacegroup": spacegroup, "quality": quality, "rir": rir,
                "score": float(score), "reference_coverage": float(reference_coverage),
                "observed_coverage": float(observed_coverage),
                "matched_count": len(matched_lines), "reference_count": len(lines),
                "matched_observed_count": len(used),
                "matched_lines": sorted(matched_lines, key=lambda item: item["reference_d_angstrom"],
                                        reverse=True),
            })
        results.sort(key=lambda item: (item["score"], item["matched_observed_count"]), reverse=True)
        return results[:top_n]
