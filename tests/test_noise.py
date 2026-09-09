import tempfile
import unittest
from pathlib import Path

from .fixtures import make_addon
from analyzer import analyze_community_with_stats
from noise import MAX_SAMPLES, _representative_sample, apply_noise_rules
from scanner import scan_community


class NoiseRulesTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.community = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _scan(self):
        addons, errors = scan_community(self.community)
        self.assertEqual(errors, [])
        issues, _ = analyze_community_with_stats(addons, full_scan=True)
        return addons, issues

    def test_large_sample_is_full_unique_and_covers_both_ends(self):
        details = [
            {"path": f"group-{index % 3}/item-{index}.txt"}
            for index in range(1000)
        ]

        sample = _representative_sample(details)

        self.assertEqual(len(sample), MAX_SAMPLES)
        self.assertEqual(len({id(item) for item in sample}), MAX_SAMPLES)
        self.assertIn(details[0], sample)
        self.assertIn(details[-1], sample)

    def test_large_crlf_to_lf_batch_is_transparently_downgraded(self):
        content = b"[section]\nvalue=1\n"
        expected_size = len(content) + content.count(b"\n")
        entries = [
            {"path": f"SimObjects/Test/config_{index}.cfg",
             "size": expected_size}
            for index in range(20)
        ]
        files = {entry["path"]: content for entry in entries}
        make_addon(self.community, "normalized",
                   layout_content=entries, files=files)

        addons, issues = self._scan()
        issue = next(
            item for item in issues
            if item["rule_id"] == "LAYOUT_FILE_SIZE_MISMATCH"
        )
        self.assertEqual(issue["severity"], "warning")

        apply_noise_rules(issues, addons)

        self.assertEqual(issue["severity"], "info")
        self.assertEqual(issue["original_severity"], "warning")
        self.assertEqual(
            issue["downgrade_rule"], "TEXT_LINE_ENDING_NORMALIZATION"
        )
        self.assertEqual(issue["downgrade_evidence"], {
            "sampled_files": 20,
            "total_files": 20,
        })

    def test_one_non_matching_file_prevents_downgrade(self):
        content = b"a\nb\n"
        expected_size = len(content) + content.count(b"\n")
        entries = [
            {"path": f"Config/item_{index}.txt", "size": expected_size}
            for index in range(19)
        ]
        files = {entry["path"]: content for entry in entries}
        entries.append({"path": "Config/other.bin", "size": 4})
        files["Config/other.bin"] = b"abc"
        make_addon(self.community, "mixed",
                   layout_content=entries, files=files)

        addons, issues = self._scan()
        issue = next(
            item for item in issues
            if item["rule_id"] == "LAYOUT_FILE_SIZE_MISMATCH"
        )
        apply_noise_rules(issues, addons)

        self.assertEqual(issue["severity"], "warning")
        self.assertNotIn("downgrade_rule", issue)

    def test_small_batch_is_not_auto_downgraded(self):
        content = b"a\n"
        make_addon(
            self.community,
            "small",
            layout_content=[{"path": "Config/a.txt", "size": 3}],
            files={"Config/a.txt": content},
        )

        addons, issues = self._scan()
        issue = next(
            item for item in issues
            if item["rule_id"] == "LAYOUT_FILE_SIZE_MISMATCH"
        )
        apply_noise_rules(issues, addons)

        self.assertEqual(issue["severity"], "warning")
        self.assertNotIn("downgrade_rule", issue)
