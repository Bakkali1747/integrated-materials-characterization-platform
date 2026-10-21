"""锁定文件必须与当前验证环境的实际版本一致。"""
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pins():
    result = {}
    for line in (ROOT / "requirements-lock.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, pinned = line.split("==")
        result[name] = pinned
    return result


def test_lockfile_matches_environment():
    for name, pinned in pins().items():
        assert version(name) == pinned, f"{name} 实际 {version(name)}，锁定 {pinned}"


def test_lockfile_covers_runtime_and_test_dependencies():
    names = set(pins())
    assert {"numpy", "pandas", "matplotlib", "openpyxl", "xlrd", "PySide6", "pytest", "pytest-qt"} <= names
