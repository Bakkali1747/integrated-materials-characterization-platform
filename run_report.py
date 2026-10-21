"""生成单样品中文分析报告（DOCX / PDF）。"""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))

from export.report import export_report


def main(argv=None):
    parser = argparse.ArgumentParser(description="从已完成运行生成中文分析报告（图内英文标签）")
    parser.add_argument("--run", required=True, help="包含 analysis_record.json 的运行目录")
    parser.add_argument("--output", required=True, help="输出基名或 .docx/.pdf 路径")
    parser.add_argument("--format", choices=["both", "docx", "pdf"], default="both")
    parser.add_argument("--dpi", type=int, default=300)
    args = parser.parse_args(argv)
    formats = ("docx", "pdf") if args.format == "both" else (args.format,)
    try:
        files = export_report(Path(args.run), Path(args.output), formats=formats, dpi=args.dpi)
    except Exception as error:
        print(f"报告生成失败：{type(error).__name__}: {error}", file=sys.stderr)
        return 1
    for path in files:
        print(f"报告：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
