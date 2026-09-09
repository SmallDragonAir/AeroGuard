import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from .fixtures import make_addon
from scanner import scan_community
from analyzer import (
    analyze_community,
    analyze_community_with_stats,
)


def scan_addons(community):
    addons, scan_errors = scan_community(community)
    assert not scan_errors, scan_errors
    return addons


class AnalyzerQuickTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.community = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _rules(self, addons, full_scan=False):
        issues, _ = analyze_community_with_stats(
            addons, full_scan=full_scan
        )
        return {issue["rule_id"] for issue in issues}

    def test_no_issues_for_healthy_addon(self):
        make_addon(
            self.community, "healthy",
            layout_content=[{"path": "a.txt", "size": 4}],
            files={"a.txt": b"1234"},
        )
        addons = scan_addons(self.community)

        self.assertEqual(self._rules(addons), set())
        self.assertEqual(self._rules(addons, full_scan=True), set())

    def test_manifest_missing_fields_warn(self):
        make_addon(
            self.community, "no-fields",
            manifest={"title": None, "content_type": None,
                      "package_version": None},
            layout_content=[],
        )
        addons = scan_addons(self.community)

        rules = self._rules(addons)
        self.assertEqual(rules, {
            "MANIFEST_MISSING_TITLE",
            "MANIFEST_MISSING_CONTENT_TYPE",
            "MANIFEST_MISSING_VERSION",
        })

    def test_missing_layout_is_info(self):
        make_addon(self.community, "no-layout")

        addons = scan_addons(self.community)
        issues, _ = analyze_community_with_stats(addons)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["rule_id"], "LAYOUT_MISSING")
        self.assertEqual(issues[0]["severity"], "info")

    def test_invalid_layout_json_is_error(self):
        addon = make_addon(self.community, "bad-layout")
        addon.joinpath("layout.json").write_text(
            "{oops", encoding="utf-8"
        )

        addons = scan_addons(self.community)
        issues, _ = analyze_community_with_stats(addons)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["rule_id"], "LAYOUT_INVALID")
        self.assertEqual(issues[0]["severity"], "error")
        self.assertIn("无法解析", issues[0]["message"])

    def test_non_object_layout_is_error_and_analysis_continues(self):
        broken = make_addon(self.community, "bad-root")
        broken.joinpath("layout.json").write_text("null", encoding="utf-8")
        make_addon(self.community, "healthy", layout_content=[])

        addons = scan_addons(self.community)
        issues, _ = analyze_community_with_stats(addons)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["package"], "bad-root")
        self.assertEqual(issues[0]["rule_id"], "LAYOUT_INVALID")
        self.assertIn("顶层必须是 JSON 对象", issues[0]["message"])

    def test_content_not_list_is_error(self):
        make_addon(self.community, "bad-content")
        layout_path = self.community / "bad-content" / "layout.json"
        layout_path.write_text('{"content": "nope"}', encoding="utf-8")

        addons = scan_addons(self.community)
        issues, _ = analyze_community_with_stats(addons)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["rule_id"], "LAYOUT_INVALID_ENTRY")
        self.assertEqual(issues[0]["severity"], "error")

    def test_duplicate_and_invalid_entries_warn(self):
        make_addon(
            self.community, "messy",
            layout_content=[
                {"path": "a.txt", "size": 7},
                {"path": "A.TXT"},                      # 重复（大小写不敏感）
                {},                                     # 缺 path
                {"path": "x.txt", "size": -1},          # size 非法
                42,                                     # 非对象
            ],
        )
        addons = scan_addons(self.community)
        issues, _ = analyze_community_with_stats(addons)

        rules = {issue["rule_id"]: issue for issue in issues}

        duplicate = rules["LAYOUT_DUPLICATE_PATH"]
        self.assertEqual(duplicate["severity"], "warning")
        self.assertEqual(duplicate["affected_count"], 1)
        self.assertEqual(duplicate["details"], ["A.TXT"])

        invalid = rules["LAYOUT_INVALID_ENTRY"]
        self.assertEqual(invalid["severity"], "warning")
        self.assertEqual(invalid["affected_count"], 3)

    def test_quick_scan_never_checks_files(self):
        # 声明的文件不存在，但快速扫描不应报缺失。
        make_addon(
            self.community, "quick-only",
            layout_content=[
                {"path": "gone.txt", "size": 1},
                {"path": "present.txt", "size": 4},
            ],
            files={"present.txt": b"1234"},
        )
        addons = scan_addons(self.community)

        self.assertEqual(self._rules(addons), set())

    def test_issue_structure_is_uniform(self):
        make_addon(
            self.community, "one",
            layout_content=[{"path": "a.txt"}, {"path": "A.txt"}],
        )
        addons = scan_addons(self.community)
        issues, _ = analyze_community_with_stats(addons)

        for issue in issues:
            self.assertIn("details", issue)
            self.assertIn("preview", issue)
            self.assertIn("affected_count", issue)
            expected_count = len(issue["details"]) or 1
            self.assertEqual(issue["affected_count"], expected_count)

    def test_package_level_issue_counts_one_affected_package(self):
        make_addon(self.community, "no-fields",
                   manifest={"title": None}, layout_content=[])
        addons = scan_addons(self.community)

        issues, _ = analyze_community_with_stats(addons)
        missing_title = next(
            issue for issue in issues
            if issue["rule_id"] == "MANIFEST_MISSING_TITLE"
        )

        self.assertEqual(missing_title["affected_count"], 1)
        self.assertEqual(missing_title["details"], [])


class AnalyzerFullScanTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.community = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_full_scan_finds_missing_size_unlisted(self):
        make_addon(
            self.community, "full",
            layout_content=[
                {"path": "ok.txt", "size": 5},
                {"path": "gone.txt", "size": 5},
                {"path": "b.txt", "size": 99},
            ],
            files={
                "ok.txt": b"hello",
                "b.txt": b"1234",
                "extra.txt": b"zzz",
            },
        )
        addons = scan_addons(self.community)
        issues, _ = analyze_community_with_stats(addons, full_scan=True)

        rules = {issue["rule_id"]: issue for issue in issues}

        missing = rules["LAYOUT_FILE_MISSING"]
        self.assertEqual(missing["severity"], "error")
        self.assertEqual(missing["details"], ["gone.txt"])

        mismatch = rules["LAYOUT_FILE_SIZE_MISMATCH"]
        self.assertEqual(mismatch["severity"], "warning")
        self.assertEqual(mismatch["details"], [{
            "path": "b.txt", "expected": 99, "actual": 4,
        }])

        unlisted = rules["LAYOUT_UNLISTED_FILE"]
        self.assertEqual(unlisted["severity"], "info")
        self.assertEqual(unlisted["details"], ["extra.txt"])

    def test_metadata_files_never_unlisted(self):
        make_addon(
            self.community, "meta",
            layout_content=[{"path": "a.txt", "size": 1}],
            files={"a.txt": b"x"},
        )
        addons = scan_addons(self.community)
        issues, _ = analyze_community_with_stats(addons, full_scan=True)

        unlisted = [
            issue for issue in issues
            if issue["rule_id"] == "LAYOUT_UNLISTED_FILE"
        ]
        self.assertEqual(unlisted, [])

    def test_os_junk_files_not_reported_unlisted(self):
        make_addon(
            self.community, "junk",
            layout_content=[{"path": "a.txt", "size": 1}],
            files={
                "a.txt": b"x",
                "Thumbs.db": b"db",
                ".DS_Store": b"ds",
                "Desktop.ini": b"di",
            },
        )
        addons = scan_addons(self.community)
        issues, _ = analyze_community_with_stats(addons, full_scan=True)

        self.assertEqual(issues, [])

    def test_details_full_and_preview_truncated(self):
        entries = [
            {"path": f"gone_{i:02d}.bin", "size": 1}
            for i in range(12)
        ]
        make_addon(self.community, "many-missing", layout_content=entries)

        addons = scan_addons(self.community)
        issues, _ = analyze_community_with_stats(addons, full_scan=True)

        missing = next(
            issue for issue in issues
            if issue["rule_id"] == "LAYOUT_FILE_MISSING"
        )
        self.assertEqual(missing["affected_count"], 12)
        self.assertEqual(len(missing["details"]), 12)
        self.assertEqual(len(missing["preview"]), 10)
        # preview 是 details 的前 10 项
        self.assertEqual(
            missing["preview"], missing["details"][:10]
        )

    def test_compat_entry_returns_issues_only(self):
        make_addon(
            self.community, "healthy",
            layout_content=[{"path": "a.txt", "size": 1}],
            files={"a.txt": b"x"},
        )
        addons = scan_addons(self.community)

        issues_only = analyze_community(addons, full_scan=True)
        issues_with_stats, stats = analyze_community_with_stats(
            addons, full_scan=True
        )

        self.assertEqual(issues_only, issues_with_stats)
        self.assertEqual(stats.addon_count, 1)
        self.assertGreaterEqual(stats.tree_walk_time, 0.0)
        self.assertGreaterEqual(stats.layout_parse_time, 0.0)
        self.assertEqual(stats.package_timings[0]["package"], "healthy")
        self.assertEqual(stats.package_timings[0]["file_count"], 3)

    def test_analyzer_prints_nothing(self):
        make_addon(
            self.community, "healthy",
            layout_content=[{"path": "a.txt", "size": 1}],
            files={"a.txt": b"x"},
        )
        addons = scan_addons(self.community)

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            analyze_community_with_stats(addons, full_scan=True)

        self.assertEqual(buffer.getvalue(), "")

    def test_unreadable_directory_is_incomplete_not_missing(self):
        addon = make_addon(
            self.community,
            "unreadable",
            layout_content=[{"path": "locked/real.bgl", "size": 4}],
            files={"locked/real.bgl": b"data"},
        )
        addons = scan_addons(self.community)
        real_scandir = os.scandir

        def fail_locked(path):
            if Path(path) == addon / "locked":
                raise PermissionError("simulated read denial")
            return real_scandir(path)

        with patch("analyzer.os.scandir", side_effect=fail_locked):
            issues, _ = analyze_community_with_stats(
                addons, full_scan=True
            )

        rules = {issue["rule_id"]: issue for issue in issues}
        self.assertNotIn("LAYOUT_FILE_MISSING", rules)
        self.assertIn("FILE_TREE_SCAN_INCOMPLETE", rules)
        self.assertEqual(
            rules["FILE_TREE_SCAN_INCOMPLETE"]["details"][0]["path"],
            "locked",
        )


if __name__ == "__main__":
    unittest.main()
