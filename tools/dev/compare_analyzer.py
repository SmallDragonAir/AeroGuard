import sys
from collections import defaultdict
from pathlib import Path

# 允许从任意工作目录运行：python tools/dev/compare_analyzer.py
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scanner import scan_community
from analyzer import analyze_community as analyze_new
from analyzer_old import analyze_community as analyze_old


COMMUNITY_PATH = Path(r"D:\MSFS2024_DATA\Community")


def get_size_mismatch_counts(issues):
    counts = {}

    for issue in issues:
        if issue["rule_id"] != "LAYOUT_FILE_SIZE_MISMATCH":
            continue

        counts[issue["package"]] = issue.get("affected_count", 1)

    return counts


print("扫描 Community……")
addons, scan_errors = scan_community(COMMUNITY_PATH)

print("插件数：", len(addons))
print("扫描异常：", len(scan_errors))


print("\n运行旧版 Analyzer……")
old_issues = analyze_old(addons, full_scan=True)

print("\n运行新版 Analyzer……")
new_issues = analyze_new(addons, full_scan=True)


old_counts = get_size_mismatch_counts(old_issues)
new_counts = get_size_mismatch_counts(new_issues)


print(
    "旧版 SIZE_MISMATCH 总数：",
    sum(old_counts.values())
)

print(
    "新版 SIZE_MISMATCH 总数：",
    sum(new_counts.values())
)



print("\n=== SIZE_MISMATCH 差异 ===")

all_packages = sorted(
    set(old_counts) | set(new_counts)
)

difference_found = False

for package in all_packages:
    old_count = old_counts.get(package, 0)
    new_count = new_counts.get(package, 0)

    if old_count != new_count:
        difference_found = True

        print(
            f"{package}: "
            f"旧版 {old_count} -> 新版 {new_count} "
            f"(差值 {new_count - old_count:+d})"
        )


if not difference_found:
    print("未发现 Package 级数量差异。")