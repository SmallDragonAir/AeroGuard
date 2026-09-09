import unittest

from analyzer import make_issue as make_analyzer_issue
from report import (
    build_report,
    group_issues_by_package,
    missing_file_issues,
    package_risk,
    rank_missing_issues,
    rule_summary,
    top_issues,
    top_risk_packages,
)


def make_issue(rule_id, package, severity="warning",
               affected=1, impact="unknown"):
    return {
        "rule_id": rule_id,
        "severity": severity,
        "package": package,
        "message": rule_id,
        "affected_count": affected,
        "details": ["x"] * affected,
        "preview": ["x"] * min(affected, 10),
        "impact": impact,
    }


ISSUES = [
    make_issue("LAYOUT_FILE_MISSING", "alpha", "error", 20,
               "potentially_runtime"),
    make_issue("LAYOUT_FILE_MISSING", "beta", "error", 3,
               "likely_non_runtime"),
    make_issue("LAYOUT_UNLISTED_FILE", "alpha", "info", 2),
    make_issue("MANIFEST_MISSING_TITLE", "gamma", "warning", 1),
    make_issue("LAYOUT_FILE_MISSING", "alpha", "error", 5,
               "unknown"),
]


class ReportAggregationTest(unittest.TestCase):

    def test_package_level_issue_contributes_one_affected_item(self):
        issue = make_analyzer_issue(
            "MANIFEST_MISSING_TITLE", "warning", "alpha", "missing"
        )

        self.assertEqual(rule_summary([issue])[0]["affected"], 1)
        self.assertEqual(package_risk([issue])["alpha"]["affected"], 1)

    def test_rule_summary_counts_packages_and_affected(self):
        summary = rule_summary(ISSUES)
        by_rule = {item["rule_id"]: item for item in summary}

        self.assertEqual(by_rule["LAYOUT_FILE_MISSING"]["packages"], 2)
        self.assertEqual(
            by_rule["LAYOUT_FILE_MISSING"]["affected"], 28
        )
        self.assertEqual(by_rule["LAYOUT_UNLISTED_FILE"]["packages"], 1)
        # 按命中插件数降序
        self.assertEqual(summary[0]["rule_id"], "LAYOUT_FILE_MISSING")

    def test_group_issues_by_package(self):
        grouped = group_issues_by_package(ISSUES)

        self.assertEqual(set(grouped), {"alpha", "beta", "gamma"})
        self.assertEqual(len(grouped["alpha"]), 3)

    def test_top_issues_sorted_by_affected(self):
        top = top_issues(ISSUES, limit=3)
        counts = [issue["affected_count"] for issue in top]
        self.assertEqual(counts, [20, 5, 3])

    def test_package_risk_and_ranking(self):
        risk = package_risk(ISSUES)

        self.assertEqual(risk["alpha"]["error"], 2)
        self.assertEqual(risk["alpha"]["warning"], 0)
        self.assertEqual(risk["alpha"]["info"], 1)
        self.assertEqual(risk["alpha"]["affected"], 27)

        top = top_risk_packages(ISSUES, limit=10)
        self.assertEqual(top[0][0], "alpha")
        self.assertEqual(top[0][1]["error"], 2)

    def test_missing_and_rank_by_impact(self):
        missing = missing_file_issues(ISSUES)
        self.assertEqual(len(missing), 3)

        ranked = rank_missing_issues(missing)
        packages = [issue["package"] for issue in ranked]
        # runtime(20) > unknown(5) > non_runtime(3)
        self.assertEqual(packages, ["alpha", "alpha", "beta"])

        limited = rank_missing_issues(missing, limit=2)
        self.assertEqual(len(limited), 2)


class BuildReportTest(unittest.TestCase):

    def test_build_report_document(self):
        addons = [{
            "folder_name": "alpha",
            "name": "Alpha",
            "type": "AIRCRAFT",
            "creator": "me",
            "version": "1.0",
            "path": "C:/Community/alpha",
            "manifest": {"secret": True},  # 不应出现在报告中
        }]

        timing = {"scanner": 0.1234, "analyzer": 2.0,
                  "classifier": 0.05, "total": 2.2}
        issues = [dict(issue) for issue in ISSUES]
        issues[0]["original_severity"] = "error"
        issues[0]["downgrade_rule"] = "TEST_DOWNGRADE"

        class FakeStats:
            def as_dict(self):
                return {"layout_parse_time": 0.5}

        class FakeRelationships:
            def as_dict(self):
                return {
                    "summary": {
                        "resource_conflicts": 3,
                        "airport_conflicts": 1,
                    },
                    "resource_conflicts": [{"path": "Effects/shared.fx"}],
                    "airport_packages": [],
                    "airport_conflicts": [],
                    "dependencies": [],
                    "dependency_cycles": [],
                }

        doc = build_report(
            community_path="C:/Community",
            scan_mode="full",
            addons=addons,
            scan_errors=[{"package": "x", "path": "y", "error": "z"}],
            issues=issues,
            stats=FakeStats(),
            timing=timing,
            relationships=FakeRelationships(),
        )

        self.assertEqual(doc["schema_version"], 1)
        self.assertEqual(doc["tool"], "aeroguard")
        self.assertEqual(doc["scan_mode"], "full")
        self.assertEqual(doc["summary"]["addons"], 1)
        self.assertEqual(doc["summary"]["issues"], 5)
        self.assertEqual(doc["summary"]["scan_errors"], 1)
        self.assertEqual(doc["summary"]["packages_with_issues"], 3)
        self.assertEqual(doc["summary"]["downgraded_issues"], 1)
        self.assertEqual(doc["summary"]["downgraded_affected"], 20)
        self.assertEqual(doc["summary"]["resource_conflicts"], 3)
        self.assertEqual(doc["summary"]["airport_conflicts"], 1)
        self.assertEqual(doc["timing"]["scanner_s"], 0.123)
        self.assertEqual(doc["timing"]["noise_filter_s"], 0.0)
        self.assertEqual(doc["timing"]["relationships_s"], 0.0)
        self.assertEqual(doc["timing"]["analyzer_internal"],
                         {"layout_parse_time": 0.5})
        self.assertEqual(len(doc["addons"]), 1)
        self.assertNotIn("manifest", doc["addons"][0])
        self.assertEqual(doc["scan_errors"][0]["package"], "x")
        self.assertEqual(doc["issues_by_package"]["alpha"][0]["rule_id"],
                         "LAYOUT_FILE_MISSING")
        self.assertEqual(doc["relationships"]["summary"]
                         ["resource_conflicts"], 3)


if __name__ == "__main__":
    unittest.main()
