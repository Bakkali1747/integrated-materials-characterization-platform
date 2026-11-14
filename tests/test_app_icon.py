"""应用图标资产与打包配置的回归测试。"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def test_app_icon_assets_and_packaging_references():
    png = ROOT / "assets" / "app.png"
    ico = ROOT / "assets" / "app.ico"
    assert png.is_file() and ico.is_file()
    image = Image.open(png)
    assert image.size == (1024, 1024)
    ico_image = Image.open(ico)
    assert {(16, 16), (32, 32), (256, 256)}.issubset(set(ico_image.info.get("sizes", set())))
    assert "assets/app.ico" in (ROOT / "packaging" / "client.spec").read_text(encoding="utf-8")
    assert "SetupIconFile=..\\assets\\app.ico" in (ROOT / "packaging" / "client.iss").read_text(encoding="utf-8")
