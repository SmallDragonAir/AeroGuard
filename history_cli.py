"""AeroGuard 扫描历史与环境基线命令行入口。"""

import argparse
import json
import sys
from pathlib import Path

from history import HistoryError, HistoryStore, build_snapshot, compare_snapshots
from i18n import localize_text, tr
from main import run_diagnosis_with_context
from report import build_report


def _print_json(document):
    print(json.dumps(document, ensure_ascii=False, indent=2))


def _compare_summary(comparison):
    """把基线比较文档浓缩成一行人类可读摘要。"""
    summary = comparison.get("summary", {})
    section_counts = []
    for section, counts in summary.get("sections", {}).items():
        total = sum(counts.values())
        if total:
            section_counts.append(
                f"{section} {tr('cli.count_items', n=total)}"
            )
    detail = (
        "、".join(section_counts) if section_counts
        else tr("cli.compare_no_diff")
    )
    return tr(
        "cli.compare_summary",
        name=comparison.get("baseline_name", ""),
        changes=summary.get("total_changes", 0),
        detail=detail,
        warnings=summary.get("compatibility_warnings", 0),
    )


def _run_report(community_path, mode, state_dir=None):
    addons, scan_errors, issues, stats, relationships, timing = (
        run_diagnosis_with_context(
            community_path, full_scan=(mode == "full"), state_dir=state_dir
        )
    )
    return build_report(
        community_path=community_path,
        scan_mode=mode,
        addons=addons,
        scan_errors=scan_errors,
        issues=issues,
        stats=stats,
        timing=timing,
        relationships=relationships,
    )


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="aeroguard-history",
        description=tr("help.history.description"),
    )
    parser.add_argument("community_path")
    parser.add_argument("--state-dir")
    commands = parser.add_subparsers(dest="command", required=True)

    record = commands.add_parser("record", help=tr("help.history.record"))
    record.add_argument("--mode", choices=("quick", "full"), default="quick")
    record.add_argument("--label")

    listing = commands.add_parser("list", help=tr("help.history.list"))
    listing.add_argument("--limit", type=int, default=20)

    baseline = commands.add_parser(
        "baseline-set", help=tr("help.history.baseline_set")
    )
    baseline.add_argument("name")
    baseline.add_argument("--snapshot")
    baseline.add_argument("--replace", action="store_true")

    compare = commands.add_parser(
        "compare", help=tr("help.history.compare")
    )
    compare.add_argument("name")
    compare.add_argument("--mode", choices=("quick", "full"), default="quick")
    compare.add_argument("--record", action="store_true")
    compare.add_argument("--label")
    return parser


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    args = _build_parser().parse_args(argv)
    try:
        community = Path(args.community_path).expanduser().resolve()
        store = HistoryStore(community, args.state_dir)
        if args.command == "record":
            result = store.record(
                _run_report(community, args.mode, args.state_dir),
                label=args.label
            )
        elif args.command == "list":
            if args.limit < 1:
                raise HistoryError("--limit 必须大于 0")
            snapshots = store.list_snapshots(limit=args.limit)
            result = {"count": len(snapshots), "snapshots": snapshots}
        elif args.command == "baseline-set":
            result = store.set_baseline(
                args.name, snapshot_id=args.snapshot, replace=args.replace
            )
        elif args.command == "compare":
            report = _run_report(community, args.mode, args.state_dir)
            if args.record:
                current = store.record(report, label=args.label)
                baseline = store.load_baseline(args.name)
                result = compare_snapshots(baseline, current)
                result["baseline_name"] = args.name
            else:
                result = store.compare(args.name, report)
        else:
            raise AssertionError(f"未处理的命令：{args.command}")
        _print_json(result)
        if args.command == "compare":
            print(_compare_summary(result), file=sys.stderr)
        return 0
    except HistoryError as error:
        print(
            tr("cli.history_failed", error=localize_text(str(error))),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
