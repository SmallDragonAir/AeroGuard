"""
报告聚合层：把 issues / addons / 统计转换为结构化的汇总数据。

这里只做纯数据计算，不负责终端打印或文件读写；
main.py（CLI）与未来的 GUI 都可以复用这些函数。
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone


SCHEMA_VERSION = 1


# 缺失类问题按 impact 排序时的优先级。
IMPACT_PRIORITY = {
    "potentially_runtime": 3,
    "unknown": 2,
    "likely_non_runtime": 1,
}


def group_issues_by_package(issues):
    """按 package（文件夹名）聚合 issue，保持插件内原有顺序。"""
    grouped = defaultdict(list)

    for issue in issues:
        grouped[issue["package"]].append(issue)

    return grouped


def rule_summary(issues):
    """
    按规则统计命中情况。

    返回按命中插件数降序的列表：
    [{"rule_id": ..., "packages": n, "affected": m}, ...]

    packages 统计的是受影响的插件数量（去重），
    affected 统计所有相关 issue 的受影响项目总数。
    """
    rule_packages = defaultdict(set)
    rule_affected = Counter()
    order = []

    for issue in issues:
        rule_id = issue["rule_id"]

        if rule_id not in rule_packages:
            order.append(rule_id)

        rule_packages[rule_id].add(issue["package"])
        rule_affected[rule_id] += issue.get("affected_count", 1)

    order.sort(
        key=lambda rule_id: len(rule_packages[rule_id]),
        reverse=True,
    )

    return [
        {
            "rule_id": rule_id,
            "packages": len(rule_packages[rule_id]),
            "affected": rule_affected[rule_id],
        }
        for rule_id in order
    ]


def top_issues(issues, limit=10):
    """按受影响项目数降序取前 limit 条 issue。"""
    return sorted(
        issues,
        key=lambda issue: issue.get("affected_count", 1),
        reverse=True,
    )[:limit]


def package_risk(issues):
    """按插件聚合各严重等级命中数与受影响项目数。"""
    risk = defaultdict(lambda: {
        "error": 0,
        "warning": 0,
        "info": 0,
        "affected": 0,
    })

    for issue in issues:
        package = issue["package"]
        severity = issue["severity"]

        risk[package][severity] += 1
        risk[package]["affected"] += issue.get("affected_count", 1)

    return risk


def top_risk_packages(issues, limit=10):
    """按 (error, warning, info, affected) 降序取前 limit 个插件。"""
    risk = package_risk(issues)

    return sorted(
        risk.items(),
        key=lambda item: (
            item[1]["error"],
            item[1]["warning"],
            item[1]["info"],
            item[1]["affected"],
        ),
        reverse=True,
    )[:limit]


def missing_file_issues(issues):
    """筛选 LAYOUT_FILE_MISSING 规则的问题。"""
    return [
        issue
        for issue in issues
        if issue["rule_id"] == "LAYOUT_FILE_MISSING"
    ]


def rank_missing_issues(missing_issues, limit=None):
    """
    缺失文件问题按 (impact 优先级, 受影响数) 降序排列。

    等 classifier 稳定后，可逐步由更细的 impact 数据驱动。
    """
    ranked = sorted(
        missing_issues,
        key=lambda issue: (
            IMPACT_PRIORITY.get(issue.get("impact", "unknown"), 0),
            issue.get("affected_count", 1),
        ),
        reverse=True,
    )

    if limit is not None:
        return ranked[:limit]

    return ranked


def _addon_brief(addons):
    """报告中使用的插件精简信息（不含原始 manifest，保持报告轻量）。"""
    return [
        {
            "folder_name": addon["folder_name"],
            "name": addon["name"],
            "type": addon["type"],
            "creator": addon["creator"],
            "version": addon["version"],
            "path": addon["path"],
        }
        for addon in addons
    ]


def build_report(
    *,
    community_path,
    scan_mode,
    addons,
    scan_errors,
    issues,
    stats,
    timing,
    relationships=None,
):
    """
    构造完整的、可直接 json.dump 的报告文档。

    timing: 主流程各阶段耗时（秒）字典。
    stats: analyzer.AnalyzerStats 或 None。
    """
    rule_summary_list = rule_summary(issues)
    issues_by_package = {
        package: package_issues
        for package, package_issues in group_issues_by_package(issues).items()
    }
    downgraded = [issue for issue in issues if "downgrade_rule" in issue]
    relationship_document = (
        relationships.as_dict() if relationships is not None else None
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "aeroguard",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "community_path": str(community_path),
        "scan_mode": scan_mode,
        "summary": {
            "addons": len(addons),
            "scan_errors": len(scan_errors),
            "issues": len(issues),
            "packages_with_issues": len(issues_by_package),
            "downgraded_issues": len(downgraded),
            "downgraded_affected": sum(
                issue["affected_count"] for issue in downgraded
            ),
            "resource_conflicts": (
                relationship_document["summary"]["resource_conflicts"]
                if relationship_document is not None else 0
            ),
            "airport_conflicts": (
                relationship_document["summary"]["airport_conflicts"]
                if relationship_document is not None else 0
            ),
        },
        "timing": {
            "scanner_s": round(timing.get("scanner", 0.0), 3),
            "analyzer_s": round(timing.get("analyzer", 0.0), 3),
            "noise_filter_s": round(timing.get("noise_filter", 0.0), 3),
            "classifier_s": round(timing.get("classifier", 0.0), 3),
            "relationships_s": round(timing.get("relationships", 0.0), 3),
            "total_s": round(timing.get("total", 0.0), 3),
            "analyzer_internal": (
                stats.as_dict() if stats is not None else None
            ),
        },
        "rule_summary": rule_summary_list,
        "scan_errors": list(scan_errors),
        "addons": _addon_brief(addons),
        "issues_by_package": issues_by_package,
        "relationships": relationship_document,
    }
