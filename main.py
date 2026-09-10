"""AeroGuard 命令行入口（开发版）。

支持交互与非交互两种用法：

    python main.py                          # 交互输入路径与模式
    python main.py <路径> --mode quick       # 非交互快速扫描
    python main.py <路径> --mode full --json # 完整扫描并输出 JSON 报告

只进行只读扫描，不会修改任何插件文件。
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from scanner import scan_community
from analyzer import analyze_community_with_stats
from classifier import classify_issues
from noise import apply_noise_rules
from relationships import analyze_relationships
from i18n import localize_text, tr
from export import export_html, export_markdown
from update import UpdateError, check_for_update
from notes import NoteStore, NoteStoreError
from overrides import OverrideStore, OverrideStoreError
from knowledge import apply_known_context
from report import (
    build_report,
    group_issues_by_package,
    missing_file_issues,
    rank_missing_issues,
    rule_summary,
    top_issues,
    top_risk_packages,
)


def _reconfigure_stdout():
    """让重定向/管道输出也使用 UTF-8，避免中文乱码。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="aeroguard",
        description=tr("help.main.description"),
        epilog=tr("help.main.epilog"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "community_path",
        nargs="?",
        help=tr("help.main.community"),
    )
    parser.add_argument(
        "--mode",
        choices=["quick", "full"],
        help=tr("help.main.mode"),
    )
    parser.add_argument(
        "--json",
        nargs="?",
        const="",
        metavar="PATH",
        help=tr("help.main.json"),
    )
    parser.add_argument(
        "--no-relationships",
        action="store_true",
        help=tr("help.main.no_relationships"),
    )
    parser.add_argument(
        "--state-dir",
        help=tr("help.main.state_dir"),
    )
    parser.add_argument(
        "--markdown",
        nargs="?",
        const="",
        metavar="PATH",
        help=tr("help.main.markdown"),
    )
    parser.add_argument(
        "--html",
        nargs="?",
        const="",
        metavar="PATH",
        help=tr("help.main.html"),
    )
    parser.add_argument(
        "--check-update",
        action="store_true",
        help=tr("help.main.check_update"),
    )
    return parser.parse_args(argv)


def run_update_check():
    """检查 AeroGuard 自身更新并打印结果（唯一联网操作，只读）。"""
    try:
        result = check_for_update()
    except UpdateError as error:
        print(
            tr("cli.update_failed", error=localize_text(str(error))),
            file=sys.stderr,
        )
        return 2

    print(tr("report.update.current", version=result["current_version"]))
    print(tr("report.update.latest", version=result["latest_version"]))
    if not result.get("version_comparable", True):
        print(tr("report.update.uncomparable", tag=result.get("tag", "")))
    elif result["update_available"]:
        print(tr(
            "report.update.available",
            latest=result["latest_version"],
            current=result["current_version"],
        ))
    else:
        print(tr("report.update.up_to_date", version=result["current_version"]))
    print(tr("report.update.release_url", url=result["release_url"]))
    print(tr("report.update.no_download"))
    return 0


def collect_input(args):
    """解析参数，缺失的交互式询问，返回 (community_path, mode)。"""
    community_path = args.community_path

    if community_path is None:
        community_path = input(tr("report.prompt_path"))

    community_path = Path(community_path.strip().strip('"'))

    mode = args.mode

    if mode is None:
        choice = input(tr("report.prompt_mode")).strip()
        mode = "full" if choice == "2" else "quick"

    return community_path, mode


def print_text_report(*, community_path, scan_mode, addons, scan_errors,
                      issues, stats, timing, relationships=None):
    """向终端打印可读的报告文本（按当前语言）。"""
    print(tr("report.community_path", path=community_path))
    print(tr(
        "report.scan_mode",
        mode=(tr("report.mode_full") if scan_mode == "full"
              else tr("report.mode_quick")),
    ))
    print(tr("report.addons", n=len(addons)))
    print(tr("report.scan_errors", n=len(scan_errors)))
    print(tr("report.issues", n=len(issues)))
    downgraded = [issue for issue in issues if "downgrade_rule" in issue]
    if downgraded:
        print(tr(
            "report.downgraded",
            n=len(downgraded),
            affected=sum(
                issue["affected_count"] for issue in downgraded
            ),
        ))
    if relationships is not None:
        relation_summary = relationships.summary()
        print(tr("report.resource_conflicts",
                 n=relation_summary["resource_conflicts"]))
        print(tr("report.airport_conflicts",
                 n=relation_summary["airport_conflicts"]))
        print(tr("report.declared_dependencies",
                 n=relation_summary["declared_dependencies"]))

    # === 1. 按规则统计 ===
    print(tr("report.by_rule"))

    for item in rule_summary(issues):
        affected_part = (
            tr("report.rule_affected", n=item["affected"])
            if item["affected"] else ""
        )
        print(tr(
            "report.rule_line",
            rule=item["rule_id"],
            packages=item["packages"],
            affected=affected_part,
        ))

    # === 2. 异常数量排行 ===
    print(tr("report.top_issues"))

    for issue in top_issues(issues, limit=10):
        print(
            f"{issue['package']}: "
            f"{issue['rule_id']} - "
            f"{issue.get('affected_count', 1)}"
        )

    # === 3. 按插件汇总 ===
    print(tr("report.by_package"))

    for package, package_issues in group_issues_by_package(issues).items():
        print("\n", package)

        for issue in package_issues:
            affected = issue.get("affected_count", 1)
            suffix = (
                tr("report.issue_suffix", n=affected) if affected > 1 else ""
            )

            print(tr(
                "report.issue_line",
                severity=issue['severity'].upper(),
                rule=issue['rule_id'],
                message=issue['message'],
                suffix=suffix,
            ))
            if "downgrade_rule" in issue:
                print(tr(
                    "report.downgrade_note",
                    reason=issue['downgrade_reason'],
                    n=issue['downgrade_evidence']['sampled_files'],
                ))

    # === 4. 缺失文件详情 ===
    print(tr("report.missing_detail"))

    for issue in missing_file_issues(issues):
        print(tr("report.missing_for",
                 package=issue['package'], n=issue['affected_count']))

        for file_path in issue.get("preview", []):
            print(tr("report.missing_item", path=file_path))

        hidden_count = (
            issue["affected_count"] - len(issue.get("preview", []))
        )
        if hidden_count > 0:
            print(tr("report.missing_more", n=hidden_count))

    # === 5. 重点复核排行 ===
    print(tr("report.review_top"))

    for package, stats_dict in top_risk_packages(issues, limit=10):
        print(tr(
            "report.review_line",
            package=package,
            error=stats_dict['error'],
            warning=stats_dict['warning'],
            info=stats_dict['info'],
            affected=stats_dict['affected'],
        ))

    # === 6. 缺失文件按影响复核 ===
    # 当前主要根据 impact 与受影响项目数量排序。
    print(tr("report.missing_review"))

    for issue in rank_missing_issues(missing_file_issues(issues)):
        print(tr(
            "report.missing_review_line",
            package=issue['package'],
            impact=issue.get('impact', 'unknown').upper(),
            n=issue.get('affected_count', 1),
        ))

    # === 7. 跨 Package 关系 ===
    if relationships is not None:
        print(tr("report.rel_conflicts"))
        for conflict in relationships.resource_conflicts[:10]:
            package_names = ", ".join(
                item["package"] for item in conflict["packages"]
            )
            print(tr(
                "report.rel_conflict_line",
                severity=conflict['severity'].upper(),
                path=conflict['path'],
                packages=package_names,
            ))
            print(tr("report.judgement", reason=conflict['reason']))
            if conflict["likely_winner"] is not None:
                print(tr(
                    "report.default_priority",
                    package=conflict["likely_winner"]["package"],
                    basis=conflict["likely_winner"]["basis"],
                ))

        print(tr("report.airports"))
        if not relationships.airport_conflicts:
            print(tr("report.airports_none"))
        for conflict in relationships.airport_conflicts:
            package_names = ", ".join(
                item["package"] for item in conflict["packages"]
            )
            print(tr(
                "report.rel_conflict_line",
                severity=conflict['severity'].upper(),
                path=conflict['airport_code'],
                packages=package_names,
            ))
            print(tr("report.judgement", reason=conflict['reason']))

        summary = relationships.summary()
        print(tr("report.deps"))
        print(tr(
            "report.deps_resolved",
            n=summary["dependencies_resolved_in_scan_root"],
        ))
        print(tr(
            "report.deps_outside",
            n=summary["dependencies_outside_scan_scope"],
        ))
        print(tr("report.deps_invalid", n=summary["invalid_dependencies"]))
        print(tr("report.deps_cycles", n=summary["dependency_cycles"]))

    # === 8. 扫描错误明细 ===
    if scan_errors:
        print(tr("report.scan_error_detail"))

        for error in scan_errors:
            print(tr("report.scan_error_for", package=error['package']))
            print(tr("report.scan_error_path", path=error['path']))
            print(tr("report.scan_error_text", error=error['error']))

    # === 9. 性能统计 ===
    print(tr("report.performance"))
    print(tr("report.perf_line", label="Scanner",
             value=round(timing["scanner"], 2)))
    print(tr("report.perf_line", label="Analyzer",
             value=round(timing["analyzer"], 2)))
    print(tr(
        "report.perf_line",
        label=tr("report.perf_noise_label"),
        value=round(timing.get("noise_filter", 0.0), 4),
    ))
    print(tr("report.perf_line", label="Classifier",
             value=round(timing["classifier"], 4)))
    print(tr(
        "report.perf_line",
        label=tr("report.perf_relationships_label"),
        value=round(timing.get("relationships", 0.0), 3),
    ))
    print(tr("report.perf_total", value=round(timing["total"], 2)))

    if stats is not None:
        print(tr("report.perf_internal"))
        print(tr("report.perf_layout",
                 value=round(stats.layout_parse_time, 2)))
        print(tr("report.perf_declared",
                 value=round(stats.declared_check_time, 2)))
        if stats.tree_walk_wall_time:
            print(tr(
                "report.perf_tree_parallel",
                total=round(stats.tree_walk_time, 2),
                wall=round(stats.tree_walk_wall_time, 2),
            ))
        else:
            print(tr("report.perf_tree",
                     value=round(stats.tree_walk_time, 2)))
        if stats.package_timings:
            print(tr("report.perf_hotspots"))
            for item in stats.package_timings[:5]:
                print(tr(
                    "report.perf_hotspot_line",
                    package=item['package'],
                    seconds=item['tree_walk_time'],
                    files=item['file_count'],
                ))


def save_json_report(document, requested_path):
    """把报告文档写入 JSON 文件，返回写入的路径。"""
    if requested_path == "":
        default_name = (
            "aeroguard_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        output_path = Path("reports") / default_name
    else:
        output_path = Path(requested_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(document, f, ensure_ascii=False, indent=2)

    return output_path


def save_text_report(text, requested_path, extension):
    """把文本报告写入文件（.md / .html），返回写入路径。"""
    if requested_path == "":
        default_name = (
            "aeroguard_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}{extension}"
        )
        output_path = Path("reports") / default_name
    else:
        output_path = Path(requested_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        file.write(text)

    return output_path


def run_scan(community_path, full_scan):
    """执行扫描-分析-降噪-分类流程，返回各阶段产物与计时。

    跨 Package 关系分析不在本函数内执行，由 run_full_diagnosis
    （CLI / GUI / 历史记录共用）统一负责并计时。
    """
    timing = {}

    start_time = time.perf_counter()

    scanner_start = time.perf_counter()
    addons, scan_errors = scan_community(community_path)
    timing["scanner"] = time.perf_counter() - scanner_start

    analyzer_start = time.perf_counter()
    issues, stats = analyze_community_with_stats(
        addons, full_scan=full_scan
    )
    timing["analyzer"] = time.perf_counter() - analyzer_start

    noise_start = time.perf_counter()
    issues = apply_noise_rules(issues, addons)
    timing["noise_filter"] = time.perf_counter() - noise_start

    classifier_start = time.perf_counter()
    issues = classify_issues(issues)
    timing["classifier"] = time.perf_counter() - classifier_start

    timing["total"] = time.perf_counter() - start_time

    return addons, scan_errors, issues, stats, timing


def run_full_diagnosis(community_path, full_scan, *, with_relationships=True):
    """完整诊断流程：run_scan +（可选）跨 Package 关系分析。

    返回 (addons, scan_errors, issues, stats, relationships, timing)。
    relationships 在 with_relationships=False 时为 None（跳过分析以
    缩短快速扫描耗时）。供 CLI（main.main）、桌面界面
    （gui.run_desktop_scan）与历史记录（history_cli._run_report）共用。
    """
    addons, scan_errors, issues, stats, timing = run_scan(
        community_path, full_scan=full_scan
    )

    if not with_relationships:
        return addons, scan_errors, issues, stats, None, timing

    relationships_start = time.perf_counter()
    relationships = analyze_relationships(addons)
    timing["relationships"] = time.perf_counter() - relationships_start
    timing["total"] += timing["relationships"]

    return addons, scan_errors, issues, stats, relationships, timing


def run_diagnosis_with_context(community_path, full_scan, *, state_dir=None,
                               with_relationships=True):
    """在完整诊断之上应用本地知识上下文（notes 匹配 + 规则覆盖）。

    与 run_full_diagnosis 同构；state_dir 缺省时使用 Community 同级的
    .aeroguard（与 manage / history 默认一致），以便自动关联已有
    已知结论与覆盖规则。stores 不存在或损坏时静默跳过，不影响扫描。
    """
    addons, scan_errors, issues, stats, relationships, timing = (
        run_full_diagnosis(
            community_path, full_scan,
            with_relationships=with_relationships,
        )
    )

    knowledge_start = time.perf_counter()

    note_store = None
    try:
        note_store = NoteStore(community_path, state_dir)
    except NoteStoreError:
        note_store = None
    override_store = None
    try:
        override_store = OverrideStore(community_path, state_dir)
    except OverrideStoreError:
        override_store = None

    issues = apply_known_context(
        issues, addons,
        note_store=note_store, override_store=override_store,
    )

    timing["knowledge"] = time.perf_counter() - knowledge_start
    timing["total"] += timing["knowledge"]

    return addons, scan_errors, issues, stats, relationships, timing


def main(argv=None):
    _reconfigure_stdout()

    args = parse_args(argv)

    if getattr(args, "check_update", False):
        return run_update_check()

    try:
        community_path, mode = collect_input(args)
    except EOFError:
        print(tr("report.eof_hint"), file=sys.stderr)
        return 2

    if not community_path.exists():
        print(tr("report.path_missing"))
        return 1

    if not community_path.is_dir():
        print(tr("report.path_not_dir"))
        return 1

    addons, scan_errors, issues, stats, relationships, timing = (
        run_diagnosis_with_context(
            community_path,
            full_scan=(mode == "full"),
            state_dir=args.state_dir,
            with_relationships=not args.no_relationships,
        )
    )

    print_text_report(
        community_path=community_path,
        scan_mode=mode,
        addons=addons,
        scan_errors=scan_errors,
        issues=issues,
        stats=stats,
        timing=timing,
        relationships=relationships,
    )

    if (args.json is not None or args.markdown is not None
            or args.html is not None):
        document = build_report(
            community_path=community_path,
            scan_mode=mode,
            addons=addons,
            scan_errors=scan_errors,
            issues=issues,
            stats=stats,
            timing=timing,
            relationships=relationships,
        )
        if args.json is not None:
            output_path = save_json_report(document, args.json)
            print(tr("report.json_saved", path=output_path))
        if args.markdown is not None:
            output_path = save_text_report(
                export_markdown(document), args.markdown, ".md"
            )
            print(tr("report.markdown_saved", path=output_path))
        if args.html is not None:
            output_path = save_text_report(
                export_html(document), args.html, ".html"
            )
            print(tr("report.html_saved", path=output_path))

    return 0


if __name__ == "__main__":
    sys.exit(main())
