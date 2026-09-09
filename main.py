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
        description="AeroGuard —— MSFS 插件一致性诊断工具（开发版 CLI）。",
        epilog=(
            "示例：\n"
            "  python main.py\n"
            "  python main.py D:\\MSFS2024_DATA\\Community --mode full\n"
            "  python main.py <路径> --mode quick --json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "community_path",
        nargs="?",
        help="MSFS Community 文件夹路径（缺省时交互输入）",
    )
    parser.add_argument(
        "--mode",
        choices=["quick", "full"],
        help="扫描模式：quick=快速扫描，full=完整扫描（缺省时交互选择）",
    )
    parser.add_argument(
        "--json",
        nargs="?",
        const="",
        metavar="PATH",
        help=(
            "同时把完整报告写入 JSON 文件；"
            "不写 PATH 时自动保存到 reports/ 目录"
        ),
    )
    parser.add_argument(
        "--no-relationships",
        action="store_true",
        help="跳过跨 Package 冲突/依赖分析（快速扫描可明显提速）",
    )
    return parser.parse_args(argv)


def collect_input(args):
    """解析参数，缺失的交互式询问，返回 (community_path, mode)。"""
    community_path = args.community_path

    if community_path is None:
        community_path = input("请输入 MSFS Community 文件夹路径：")

    community_path = Path(community_path.strip().strip('"'))

    mode = args.mode

    if mode is None:
        choice = input("扫描模式[1=快速扫描/2=完整扫描]：").strip()
        mode = "full" if choice == "2" else "quick"

    return community_path, mode


def print_text_report(*, community_path, scan_mode, addons, scan_errors,
                      issues, stats, timing, relationships=None):
    """向终端打印可读的报告文本。"""
    print(f"Community 路径：{community_path}")
    print(f"扫描模式：{'完整扫描' if scan_mode == 'full' else '快速扫描'}")
    print("插件总数：", len(addons))
    print("扫描异常：", len(scan_errors))
    print("检测问题：", len(issues))
    downgraded = [issue for issue in issues if "downgrade_rule" in issue]
    if downgraded:
        print(
            "自动降噪：",
            len(downgraded),
            "条问题 /",
            sum(issue["affected_count"] for issue in downgraded),
            "个项目",
        )
    if relationships is not None:
        relation_summary = relationships.summary()
        print("资源冲突候选：", relation_summary["resource_conflicts"])
        print("机场重复候选：", relation_summary["airport_conflicts"])
        print("声明依赖：", relation_summary["declared_dependencies"])

    # === 1. 按规则统计 ===
    print("\n按规则：")

    for item in rule_summary(issues):
        affected_part = (
            f" / {item['affected']} 个项目"
            if item["affected"] else ""
        )
        print(
            f"  {item['rule_id']}: "
            f"{item['packages']} 个插件{affected_part}"
        )

    # === 2. 异常数量排行 ===
    print("\n=== 异常数量 TOP 10 ===")

    for issue in top_issues(issues, limit=10):
        print(
            f"{issue['package']}: "
            f"{issue['rule_id']} - "
            f"{issue.get('affected_count', 1)}"
        )

    # === 3. 按插件汇总 ===
    print("\n=== 按插件汇总 ===")

    for package, package_issues in group_issues_by_package(issues).items():
        print("\n", package)

        for issue in package_issues:
            affected = issue.get("affected_count", 1)
            suffix = f"（影响 {affected} 项）" if affected > 1 else ""

            print(
                f"  [{issue['severity'].upper()}] "
                f"{issue['rule_id']} - "
                f"{issue['message']}{suffix}"
            )
            if "downgrade_rule" in issue:
                print(
                    f"    已降级：{issue['downgrade_reason']} "
                    f"（抽样 {issue['downgrade_evidence']['sampled_files']} 项）"
                )

    # === 4. 缺失文件详情 ===
    print("\n=== 缺失文件详情 ===")

    for issue in missing_file_issues(issues):
        print(f"\n插件：{issue['package']}（{issue['affected_count']} 项缺失）")

        for file_path in issue.get("preview", []):
            print("  缺失：", file_path)

        hidden_count = (
            issue["affected_count"] - len(issue.get("preview", []))
        )
        if hidden_count > 0:
            print(f"  … 另有 {hidden_count} 项未显示，"
                  f"可用 --json 查看完整明细")

    # === 5. 重点复核排行 ===
    print("\n=== 重点复核 TOP 10 ===")

    for package, stats_dict in top_risk_packages(issues, limit=10):
        print(
            f"{package} | "
            f"ERROR {stats_dict['error']} | "
            f"WARNING {stats_dict['warning']} | "
            f"INFO {stats_dict['info']} | "
            f"影响 {stats_dict['affected']} 项"
        )

    # === 6. 缺失文件按影响复核 ===
    # 当前主要根据 impact 与受影响项目数量排序。
    print("\n=== 缺失文件重点复核 ===")

    for issue in rank_missing_issues(missing_file_issues(issues)):
        print(
            f"{issue['package']} | "
            f"{issue.get('impact', 'unknown').upper()} | "
            f"影响 {issue.get('affected_count', 1)} 项"
        )

    # === 7. 跨 Package 关系 ===
    if relationships is not None:
        print("\n=== Package 资源冲突 TOP 10 ===")
        for conflict in relationships.resource_conflicts[:10]:
            package_names = ", ".join(
                item["package"] for item in conflict["packages"]
            )
            print(
                f"[{conflict['severity'].upper()}] {conflict['path']} | "
                f"{package_names}"
            )
            print(f"  判断：{conflict['reason']}")
            if conflict["likely_winner"] is not None:
                print(
                    "  默认优先：",
                    conflict["likely_winner"]["package"],
                    f"（{conflict['likely_winner']['basis']}）",
                )

        print("\n=== 机场重复 / 覆盖候选 ===")
        if not relationships.airport_conflicts:
            print("未发现高置信度的 Community 内机场重复候选。")
        for conflict in relationships.airport_conflicts:
            package_names = ", ".join(
                item["package"] for item in conflict["packages"]
            )
            print(
                f"[{conflict['severity'].upper()}] "
                f"{conflict['airport_code']} | "
                f"{package_names}"
            )
            print(f"  判断：{conflict['reason']}")

        summary = relationships.summary()
        print("\n=== 插件依赖分析 ===")
        print(
            "当前根目录内已解析：",
            summary["dependencies_resolved_in_scan_root"],
        )
        print(
            "扫描范围外未解析：",
            summary["dependencies_outside_scan_scope"],
        )
        print("无效依赖条目：", summary["invalid_dependencies"])
        print("依赖环：", summary["dependency_cycles"])

    # === 8. 扫描错误明细 ===
    if scan_errors:
        print("\n=== 扫描错误 ===")

        for error in scan_errors:
            print(f"\n插件：{error['package']}")
            print(f"  路径：{error['path']}")
            print(f"  错误：{error['error']}")

    # === 9. 性能统计 ===
    print("\n=== 性能统计 ===")
    print("Scanner：", round(timing["scanner"], 2), "秒")
    print("Analyzer：", round(timing["analyzer"], 2), "秒")
    print("降噪规则：", round(timing.get("noise_filter", 0.0), 4), "秒")
    print("Classifier：", round(timing["classifier"], 4), "秒")
    print("关系分析：", round(timing.get("relationships", 0.0), 3), "秒")
    print("总耗时：", round(timing["total"], 2), "秒")

    if stats is not None:
        print("  Analyzer 内部：")
        print("    Layout 解析：", round(stats.layout_parse_time, 2), "秒")
        print("    声明文件检查：", round(stats.declared_check_time, 2), "秒")
        if stats.tree_walk_wall_time:
            print(
                "    文件树遍历（线程累计 / 墙钟）：",
                round(stats.tree_walk_time, 2), "秒 /",
                round(stats.tree_walk_wall_time, 2), "秒",
            )
        else:
            print("    文件树遍历：", round(stats.tree_walk_time, 2), "秒")
        if stats.package_timings:
            print("  文件树遍历热点 TOP 5：")
            for item in stats.package_timings[:5]:
                print(
                    f"    {item['package']}："
                    f"{item['tree_walk_time']:.2f} 秒 / "
                    f"{item['file_count']} 个文件"
                )


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


def main(argv=None):
    _reconfigure_stdout()

    args = parse_args(argv)

    try:
        community_path, mode = collect_input(args)
    except EOFError:
        print(
            "没有可用的交互输入（标准输入已关闭）；请使用非交互参数：\n"
            "  python main.py <Community 路径> --mode quick|full [--json]",
            file=sys.stderr,
        )
        return 2

    if not community_path.exists():
        print("路径不存在，请检查输入的路径是否正确。")
        return 1

    if not community_path.is_dir():
        print("输入的路径不是一个目录。")
        return 1

    addons, scan_errors, issues, stats, relationships, timing = (
        run_full_diagnosis(
            community_path,
            full_scan=(mode == "full"),
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

    if args.json is not None:
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
        output_path = save_json_report(document, args.json)
        print(f"\nJSON 报告已保存：{output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
