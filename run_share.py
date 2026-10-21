"""导出可分享的脱敏运行记录；不改变原分析目录。"""

import argparse
import sys

from export.share_export import export_shareable


def main(argv=None):
    parser = argparse.ArgumentParser(description="导出脱敏的运行记录副本（移除本地绝对路径）")
    parser.add_argument("--run", required=True, help="包含 analysis_record.json 的运行目录")
    parser.add_argument("--output", required=True, help="目标目录；必须不存在或为空")
    args = parser.parse_args(argv)
    try:
        output = export_shareable(args.run, args.output)
    except (ValueError, OSError) as error:
        print(f"导出失败：{error}", file=sys.stderr)
        return 1
    print(f"可分享副本：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
