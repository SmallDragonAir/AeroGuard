from collections import Counter, defaultdict
import time
from pathlib import Path
from scanner import scan_community
from analyzer import analyze_community
from classifier import classify_issues


path_input = input("请输入 MSFS Community 文件夹路径：")

community_path = Path(path_input.strip().strip('"'))

scan_mode = input(
    "扫描模式[1=快速扫描/2=完整扫描]："
    ).strip()

full_scan = scan_mode == "2"

start_time = time.perf_counter()

if not community_path.exists():
    print("路径不存在，请检查输入的路径是否正确。")
elif not community_path.is_dir():
    print("输入的路径不是一个目录。")
else:
    addons, scan_errors = scan_community(community_path)
    issues = analyze_community(
        addons, full_scan=full_scan)

    issues = classify_issues(issues)

    print("插件总数：", len(addons))
    print("扫描异常:", len(scan_errors))
    print("检测问题:", len(issues))
    print("\n检测结果：")

rule_package_counts = Counter()
rule_affected_counts = Counter()

for issue in issues:
    rule_id = issue["rule_id"]

    # 这个规则命中了一个 package
    rule_package_counts[rule_id] += 1

    # 这个 issue 实际影响多少项
    rule_affected_counts[rule_id] += issue.get("affected_count", 1)


print("\n按规则：")

for rule_id, package_count in rule_package_counts.items():
    affected_count = rule_affected_counts[rule_id]

    print(
        f"  {rule_id}: "
        f"{package_count} 个插件 / "
        f"{affected_count} 个项目"
    )


print("\n=== 异常数量 TOP 10 ===")

sorted_issues = sorted(
    issues,
    key=lambda issue: issue.get("affected_count", 1),
    reverse=True
)

for issue in sorted_issues[:10]:
    print(
        f"{issue['package']}: "
        f"{issue['rule_id']} - "
        f"{issue.get('affected_count', 1)}"
    )


package_issues = defaultdict(list)

for issue in issues:
    package_issues[issue["package"]].append(issue)


print("\n=== 按插件汇总 ===")

for package, package_issue_list in package_issues.items():

    print("\n", package)

    for issue in package_issue_list:
        print(
            f"  [{issue['severity'].upper()}] "
            f"{issue['rule_id']} - "
            f"{issue['message']}"
        )

print("\n=== 缺失文件详情 ===")

for issue in issues:

    if issue["rule_id"] != "LAYOUT_FILE_MISSING":
        continue

    print(f"\n插件：{issue['package']}")

    for file_path in issue.get("details", []):
        print("  缺失：", file_path)

package_risk = defaultdict(lambda: {
    "error": 0,
    "warning": 0,
    "info": 0,
    "affected": 0
})

for issue in issues:
    package = issue["package"]
    severity = issue["severity"]

    package_risk[package][severity] += 1
    package_risk[package]["affected"] += issue.get("affected_count", 1)

sorted_risk = sorted(
    package_risk.items(),
    key=lambda item: (
        item[1]["error"],
        item[1]["warning"],
        item[1]["info"],
        item[1]["affected"]
    ),
    reverse=True
)

print("\n=== 重点复核 TOP 10 ===")

for package, stats in sorted_risk[:10]:

    print(
        f"{package} | "
        f"ERROR {stats['error']} | "
        f"WARNING {stats['warning']} | "
        f"INFO {stats['info']} | "
        f"影响 {stats['affected']} 项"
    )



impact_priority = {
    "potentially_runtime": 3,
    "unknown": 2,
    "likely_non_runtime": 1
}

missing_issues = [
    issue
    for issue in issues
    if issue["rule_id"] == "LAYOUT_FILE_MISSING"
]

missing_issues = sorted(
    missing_issues,
    key=lambda issue: (
        impact_priority.get(issue.get("impact", "unknown"), 0),
        issue.get("affected_count", 1)
    ),
    reverse=True
)

print("\n=== 缺失文件重点复核 ===")

for issue in missing_issues:
    print(
        f"{issue['package']} | "
        f"{issue['impact'].upper()} | "
        f"影响 {issue.get('affected_count', 1)} 项"
    )

elapsed_time = time.perf_counter() - start_time

print("扫描耗时：", round(elapsed_time, 2), "秒")

