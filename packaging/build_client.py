"""构建独立 Windows 客户端；只把已记录的代码状态写入构建清单。"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from core import __version__
    from export.provenance import git_state
    folder = ROOT / "output/packaging"
    folder.mkdir(parents=True, exist_ok=True)
    record = {**git_state(), "software_version": __version__}
    if record.get("dirty") is True and "--allow-dirty" not in sys.argv:
        raise SystemExit("构建时工作区存在未提交修改；请先提交，或显式加 --allow-dirty 生成开发版。")
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))
    # 排除开发工具（例如 Poppler）的同名 DLL，Qt 使用 Windows 系统 ICU。
    windows = Path(os.environ.get("SystemRoot", "C:/Windows"))
    os.environ["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), str(windows / "System32"), str(windows)])
    (folder / "build_info.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--distpath", str(ROOT / "output/dist"),
                    "--workpath", str(ROOT / "output/pyinstaller"), str(ROOT / "packaging/client.spec")], cwd=ROOT, check=True)
    compiler = ROOT / "output/packaging-tools/InnoSetup/ISCC.exe"
    if not compiler.exists():
        raise SystemExit("EXE 目录已生成；请安装 Inno Setup 到 output/packaging-tools/InnoSetup 后编译 client.iss。")
    subprocess.run([str(compiler), f"/DAppVersion={__version__}", str(ROOT / "packaging/client.iss")], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
