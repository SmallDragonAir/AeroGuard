import tempfile
import unittest
from pathlib import Path

from gui import (
    conflict_table_rows,
    diagnostic_summary,
    filter_rows,
    issue_row_tag,
    issue_table_rows,
    management_table_rows,
    parse_args,
    run_desktop_scan,
    sort_rows,
    _lang_code_from_display,
    _lang_display_name,
)
from relationships import RelationshipAnalysis

from .fixtures import make_addon


class RowHelpersTest(unittest.TestCase):

    def test_issue_row_tag_mapping(self):
        self.assertEqual(
            issue_row_tag({"severity": "error"}), "tag_error"
        )
        self.assertEqual(
            issue_row_tag({"severity": "warning"}), "tag_warning"
        )
        self.assertEqual(
            issue_row_tag({"severity": "info"}), "tag_info"
        )
        self.assertEqual(
            issue_row_tag({"severity": "error",
                           "override": {"action": "downgrade"}}),
            "tag_downgraded",
        )
        self.assertEqual(
            issue_row_tag({"severity": "info",
                           "original_severity": "warning"}),
            "tag_downgraded",
        )

    def test_filter_rows_by_query(self):
        rows = [
            {"values": ("ERROR", "R1", "alpha", 1, "", "msg x", "note")},
            {"values": ("INFO", "R2", "beta", 2, "", "hello", "")},
        ]
        self.assertEqual(len(filter_rows(rows, "")), 2)
        self.assertEqual(len(filter_rows(rows, "alpha")), 1)
        self.assertEqual(len(filter_rows(rows, "hello")), 1)
        self.assertEqual(len(filter_rows(rows, "MISS")), 0)

    def test_sort_rows_numeric_then_text(self):
        rows = [
            {"values": ("a", 100)},
            {"values": ("b", 2)},
            {"values": ("c", 10)},
        ]
        ascending = sort_rows(rows, 1, reverse=False)
        self.assertEqual(
            [row["values"][1] for row in ascending], [2, 10, 100]
        )
        descending = sort_rows(rows, 1, reverse=True)
        self.assertEqual(
            [row["values"][1] for row in descending], [100, 10, 2]
        )

    def test_sort_rows_text_case_insensitive(self):
        rows = [
            {"values": ("Beta",)},
            {"values": ("alpha",)},
        ]
        sorted_rows = sort_rows(rows, 0)
        self.assertEqual(
            [row["values"][0] for row in sorted_rows], ["alpha", "Beta"]
        )


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

    def test_language_display_mapping(self):
        from i18n import set_language
        set_language("zh")
        self.assertEqual(_lang_display_name(), "中文")
        set_language("en")
        self.assertEqual(_lang_display_name(), "English")
        self.assertEqual(_lang_code_from_display("中文"), "zh")
        self.assertEqual(_lang_code_from_display("English"), "en")
        # 恢复默认，避免影响同进程内后续用例
        set_language("zh")


if __name__ == "__main__":
    unittest.main()
