# PyInstaller：只收集 GUI 所用依赖，Qt 使用动态库，保留第三方许可。
from pathlib import Path
import os
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH).parent
datas = [(str(root / 'output/packaging/build_info.json'), '.'),
         (str(root / 'sample_data/synthetic_constant.csv'), 'sample_data'),
         (str(root / 'sample_data/synthetic_legacy.xls'), 'sample_data'),
         (str(root / 'docs/client_usage.md'), 'docs')]
for package in ('numpy', 'pandas', 'matplotlib', 'openpyxl', 'xlrd', 'PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'pillow'):
    datas += copy_metadata(package)

a = Analysis([str(root / 'run_gui.py')], pathex=[str(root)], binaries=[], datas=datas,
             hiddenimports=['matplotlib.backends.backend_qtagg', 'openpyxl', 'xlrd'],
             hookspath=[], runtime_hooks=[],
             excludes=['pytest', 'pytestqt', 'tkinter', 'IPython', 'scipy', 'PyQt5', 'PyQt6'],
             hooksconfig={'matplotlib': {'backends': ['Agg', 'QtAgg', 'pdf', 'svg']}})
# Windows 10+ 提供 Qt 所需的非版本化 ICU API；不能带入 Poppler 的同名版本化 ICU。
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in ('icuuc.dll', 'icuin.dll') and not Path(entry[0]).name.lower().startswith('icudt')]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MicrowaveAbsorptionAnalyzer',
          debug=False, strip=False, upx=False, console=bool(os.environ.get('CLIENT_DEBUG_CONSOLE')))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='MicrowaveAbsorptionAnalyzer')
