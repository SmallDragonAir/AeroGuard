"""单插件快速校验（verify）的单元测试。"""

import tempfile
import unittest
from pathlib import Path

from .fixtures import make_addon
from notes import NoteStore
from overrides import OverrideStore
from verify import VerifyError, verify_package


class VerifyPackageTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.community = root / "community"
        self.community.mkdir()
        self.state = root / "state"
        self.addCleanup(self._tmp.cleanup)

    def test_clean_package(self):
        make_addon(
            self.community, "clean-addon",
            layout_content=[{"path": "a.txt", "size": 1}],
            files={"a.txt": b"x"},
        )

        result = verify_package(self.community, "clean-addon", self.state)

        self.assertEqual(result["package"], "clean-addon")
        self.assertEqual(result["location"], "enabled")
        self.assertEqual(result["summary"]["issues"], 0)
        self.assertEqual(result["summary"]["error"], 0)
        self.assertIsNotNone(result["traversal"])
        self.assertGreaterEqual(result["traversal"]["file_count"], 3)

    def test_missing_and_duplicate_findings(self):
        make_addon(
            self.community, "bad-addon",
            layout_content=[
                {"path": "gone.txt", "size": 1},
                {"path": "dup.txt", "size": 1},
                {"path": "DUP.TXT", "size": 1},
            ],
        )

        result = verify_package(self.community, "bad-addon", self.state)

        rule_ids = {issue["rule_id"] for issue in result["issues"]}
        self.assertIn("LAYOUT_FILE_MISSING", rule_ids)
        self.assertIn("LAYOUT_DUPLICATE_PATH", rule_ids)
        self.assertEqual(
            result["summary"]["issues"], len(result["issues"])
        )
        self.assertGreaterEqual(result["summary"]["error"], 1)

    def test_case_insensitive_lookup(self):
        make_addon(self.community, "Mixed-Case",
                   layout_content=[], files={"a.txt": b"x"})
        result = verify_package(self.community, "mixed-case", self.state)
        self.assertEqual(result["package"], "Mixed-Case")

    def test_notes_attached_and_override_applied(self):
        make_addon(
            self.community, "known-addon",
            layout_content=[{"path": "gone.txt", "size": 1}],
        )
        NoteStore(self.community, self.state).add(
            "known-addon", "已知缺失，运行期生成", rule_id="LAYOUT_FILE_MISSING"
        )
        OverrideStore(self.community, self.state).add(
            "known-addon", "LAYOUT_FILE_MISSING", "downgrade",
            reason="runtime generated",
        )

        result = verify_package(self.community, "known-addon", self.state)

        missing = next(
            issue for issue in result["issues"]
            if issue["rule_id"] == "LAYOUT_FILE_MISSING"
        )
        self.assertEqual(missing["severity"], "info")
        self.assertEqual(missing["override"]["action"], "downgrade")
        self.assertEqual(len(missing["notes"]), 1)
        self.assertEqual(result["summary"]["notes"], 1)
        self.assertEqual(result["summary"]["downgraded"], 1)

    def test_ignore_override_marks_ignored_count(self):
        make_addon(
            self.community, "ignored-addon",
            layout_content=[{"path": "gone.txt", "size": 1}],
        )
        OverrideStore(self.community, self.state).add(
            "ignored-addon", "LAYOUT_FILE_MISSING", "ignore"
        )

        result = verify_package(self.community, "ignored-addon", self.state)

        self.assertEqual(result["summary"]["issues"], 0)
        self.assertEqual(result["summary"]["ignored_by_override"], 1)

    def test_package_not_found(self):
        with self.assertRaises(VerifyError) as context:
            verify_package(self.community, "nope", self.state)
        self.assertIn("未找到插件", str(context.exception))

    def test_invalid_manifest(self):
        target = make_addon(self.community, "broken-addon")
        target.joinpath("manifest.json").write_text(
            "{bad", encoding="utf-8"
        )
        with self.assertRaises(VerifyError):
            verify_package(self.community, "broken-addon", self.state)

    def test_missing_manifest(self):
        (self.community / "empty-addon").mkdir()
        with self.assertRaises(VerifyError):
            verify_package(self.community, "empty-addon", self.state)


if __name__ == "__main__":
    unittest.main()
