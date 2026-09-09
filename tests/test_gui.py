import tempfile
import unittest
from pathlib import Path

from gui import (
    conflict_table_rows,
    diagnostic_summary,
    issue_table_rows,
    management_table_rows,
    parse_args,
    run_desktop_scan,
)
from relationships import RelationshipAnalysis

from .fixtures import make_addon


class GuiDataTest(unittest.TestCase):

    def test_issue_rows_sort_by_severity_then_affected(self):
        issues = [
            {
                "severity": "info", "rule_id": "I", "package": "alpha",
                "affected_count": 100, "message": "info",
            },
            {
                "severity": "error", "rule_id": "E", "package": "beta",
                "affected_count": 1, "message": "error",
            },
            {
                "severity": "warning", "rule_id": "W", "package": "gamma",
                "affected_count": 5, "message": "warning",
            },
        ]

        rows = issue_table_rows(issues)

        self.assertEqual([row["values"][0] for row in rows],
                         ["ERROR", "WARNING", "INFO"])
        self.assertEqual(rows[0]["detail"]["package"], "beta")

    def test_conflict_rows_include_resource_airport_and_cycle(self):
        relationships = RelationshipAnalysis(
            resource_conflicts=[{
                "severity": "warning",
                "path": "Effects/shared.fx",
                "packages": [{"package": "alpha"}, {"package": "beta"}],
                "reason": "overlap",
            }],
            airport_conflicts=[{
                "severity": "info",
                "airport_code": "ZHCC",
                "packages": [{"package": "airport-a"}, {"package": "airport-b"}],
                "reason": "same airport",
            }],
            dependency_cycles=[["alpha", "beta"]],
        )

        rows = conflict_table_rows(relationships)

        self.assertEqual([row["values"][0] for row in rows],
                         ["资源", "机场", "依赖环"])
        self.assertIn("alpha → beta → alpha", rows[2]["values"])

    def test_management_rows_flatten_all_locations(self):
        inventory = {
            "enabled": [{"status": "enabled", "package": "alpha"}],
            "disabled": [{"status": "disabled", "package": "beta"}],
            "quarantined": [{
                "status": "quarantined", "package": "gamma",
                "error": "bad manifest",
            }],
        }

        rows = management_table_rows(inventory)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[2]["values"][5], "bad manifest")

    def test_desktop_scan_builds_json_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            community = Path(temporary)
            make_addon(
                community,
                "alpha",
                layout_content=[{
                    "path": "SimObjects/Test/panel.cfg", "size": 1,
                }],
                files={"SimObjects/Test/panel.cfg": b"x"},
            )

            result = run_desktop_scan(community, "quick")
            summary = diagnostic_summary(result)
            report = result.report_document()

        self.assertEqual(summary["addons"], 1)
        self.assertEqual(summary["issues"], 0)
        self.assertEqual(report["summary"]["addons"], 1)
        self.assertIsNotNone(report["relationships"])
        self.assertIn("relationships_s", report["timing"])

    def test_gui_arguments(self):
        args = parse_args(["C:/Community", "--mode", "full"])

        self.assertEqual(args.community_path, "C:/Community")
        self.assertEqual(args.mode, "full")


if __name__ == "__main__":
    unittest.main()
