"""输出目录维护入口：列出运行占用，按日期/样品归档旧运行；默认只预演。"""

import argparse
import json
import sys

from core.maintenance import archive_runs, delete_runs, find_duplicates, scan_runs, select_runs


def human_bytes(value):
    value = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024


def print_runs(runs):
    print(f"{'样品':<24}{'日期':<26}{'状态':<12}{'大小':>10}  相对路径")
    for run in runs:
        print(f"{str(run.get('sample') or '-')[:23]:<24}{str(run.get('analysis_date') or '-')[:25]:<26}"
              f"{str(run.get('status') or '-')[:11]:<12}{human_bytes(run['size_bytes']):>10}  {run['relative']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="查看输出占用并归档旧运行；默认只预演，不移动文件")
    parser.add_argument("--root", default="output", help="输出根目录")
    parser.add_argument("--archive-root", help="归档目录；默认 <root>/_archive")
    parser.add_argument("--list", action="store_true", help="只列出运行及占用")
    parser.add_argument("--older-than", type=float, help="只选择早于 N 天的运行")
    parser.add_argument("--sample", help="按样品名包含关系筛选")
    parser.add_argument("--status", help="按运行状态筛选，例如 failed / success")
    parser.add_argument("--all", action="store_true", help="选择全部运行（仍可用 --sample/--status 过滤）")
    parser.add_argument("--apply", action="store_true", help="真正移动/删除文件；省略时为预演")
    parser.add_argument("--delete", action="store_true", help="移入回收站而不是归档；需 --apply 执行")
    parser.add_argument("--duplicates", action="store_true", help="只列出相同样品/源哈希/配置的重复运行")
    parser.add_argument("--json", action="store_true", help="输出机器可读报告")
    args = parser.parse_args(argv)
    try:
        runs = scan_runs(args.root)
        if args.duplicates:
            groups = find_duplicates(runs)
            if args.json:
                print(json.dumps(groups, ensure_ascii=False, indent=2))
            else:
                for group in groups:
                    print(f"{group['sample']} | {group['count']} 份 | 可回收 "
                          f"{human_bytes(group['reclaimable_bytes'])} | 保留 {group['keep']}")
                    for relative in group["runs"]:
                        print(f"  重复：{relative}")
                print(f"共 {len(groups)} 组重复，可回收 "
                      f"{human_bytes(sum(group['reclaimable_bytes'] for group in groups))}。")
            return 0
        if args.list or not (args.all or args.older_than is not None or args.sample or args.status):
            print_runs(runs)
            print(f"共 {len(runs)} 个运行，占用 {human_bytes(sum(run['size_bytes'] for run in runs))}；"
                  "使用 --older-than / --sample / --status 选择后加 --apply 归档。")
            return 0
        selected = select_runs(runs, None if args.all else args.older_than, args.sample, args.status)
        if not selected:
            print("没有符合条件的运行。")
            return 0
        report = (delete_runs if args.delete else archive_runs)(
            selected, args.root, **({} if args.delete else {"archive_root": args.archive_root}),
            apply=args.apply)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            if args.delete:
                action = "已移入回收站" if args.apply else "将移入回收站（预演；加 --apply 执行）"
            else:
                action = "已归档" if args.apply else "将归档（预演；加 --apply 执行）"
            print(f"{action} {len(report['runs'])} 个运行，合计 {human_bytes(report['total_bytes'])}")
            for run in report["runs"]:
                target = run.get("archived_to") or run.get("target")
                print(f"  {run.get('sample') or '-'} | {run['relative']}" + (f" -> {target}" if target else ""))
            if not args.apply:
                print("预演未移动任何文件。")
            if report.get("failures"):
                print(f"有 {len(report['failures'])} 个运行归档失败：", file=sys.stderr)
                for failure in report["failures"]:
                    print(f"  {failure['relative']}: {failure['error']}", file=sys.stderr)
                return 1
        return 0
    except (ValueError, OSError) as error:
        print(f"维护失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
