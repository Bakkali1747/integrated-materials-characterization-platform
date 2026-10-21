"""版本号必须只有一个来源，构建配置与打包脚本跟随 core.__version__。"""
import re
import tomllib
from pathlib import Path

from core import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_version_matches_pyproject_and_installer():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == __version__
    installer = (ROOT / "packaging/client.iss").read_text(encoding="utf-8")
    match = re.search(r'#define AppVersion "([^"]+)"', installer)
    assert match and match.group(1) == __version__
