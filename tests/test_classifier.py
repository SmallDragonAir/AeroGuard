import tempfile
import unittest
from pathlib import Path

from .fixtures import make_addon
from scanner import scan_community
from analyzer import analyze_community_with_stats
from classifier import classify_file_path, classify_issues


def make_issue(rule_id, details):
    """构造用于 classifier 单测的最小 issue。"""
    return {
        "rule_id": rule_id,
        "severity": "warning",
        "package": "pkg",
        "message": "m",
        "affected_count": len(details),
        "details": list(details),
        "preview": list(details)[:10],
    }


class ClassifyFilePathTest(unittest.TestCase):

    def classify(self, file_path):
        return classify_file_path(file_path)["impact"]

    def test_doc_file_names(self):
        for name in ["readme.md", "README.TXT", "how_to_install.txt",
                     "license.md", "changelog.txt"]:
            self.assertEqual(
                self.classify(name), "likely_non_runtime", name
            )

    def test_doc_extension(self):
        self.assertEqual(
            self.classify("docs/guide.md"), "likely_non_runtime"
        )

    def test_doc_directory(self):
        self.assertEqual(
            self.classify("Documentation/install.pdf"),
            "likely_non_runtime",
        )

    def test_wasm_composite_extension(self):
        self.assertEqual(
            self.classify("html_ui/MSFS_Plugin.wasm.id0"),
            "potentially_runtime",
        )

    def test_runtime_extension(self):
        for ext_path in [
            "panel.bgl",
            "mod/wasm/module.wasm",
            "SimObjects/x/texture.cfg",
            "scripts/main.js",
            "ui/style.css",
            "sounds/engine.wav",
        ]:
            self.assertEqual(
                self.classify(ext_path), "potentially_runtime", ext_path
            )

    def test_runtime_structure_dir(self):
        # .mdl 不在扩展名单中，但位于 SimObjects 运行时目录。
        self.assertEqual(
            self.classify("SimObjects/Airplanes/x/model/x.mdl"),
            "potentially_runtime",
        )
        self.assertEqual(
            self.classify("effects/landing.fx"),
            "potentially_runtime",
        )

    def test_config_dir_txt(self):
        self.assertEqual(
            self.classify("Config/options.txt"),
            "potentially_runtime",
        )

    def test_unknown_extension_stays_unknown(self):
        self.assertEqual(
            self.classify("notes/notes.dat"), "unknown"
        )


class ClassifyIssuesTest(unittest.TestCase):

    def _run(self, issues):
        return classify_issues(issues)

    def test_aggregate_runtime_wins_over_preview_docs(self):
        """回归：分类必须基于完整 details，而非截断的预览。"""
        details = [f"docs/guide_{i:02d}.md" for i in range(11)]
        details.append("core/panel.bgl")

        issues = self._run([make_issue("LAYOUT_FILE_MISSING", details)])

        issue = issues[0]
        self.assertEqual(issue["impact"], "potentially_runtime")
        self.assertEqual(len(issue["classified_files"]), 12)

    def test_all_docs_is_likely_non_runtime(self):
        details = [
            "readme.md",
            "how_to_install.txt",
            "Documentation/guide.pdf",
            "license.md",
        ]
        issues = self._run([make_issue("LAYOUT_FILE_MISSING", details)])

        self.assertEqual(issues[0]["impact"], "likely_non_runtime")

    def test_unknown_keeps_unknown(self):
        issues = self._run([
            make_issue("LAYOUT_FILE_MISSING", ["assets/data.xyz"])
        ])
        self.assertEqual(issues[0]["impact"], "unknown")

    def test_size_mismatch_and_unlisted_are_classified(self):
        issues = self._run([
            make_issue("LAYOUT_FILE_SIZE_MISMATCH", [
                {"path": "SimObjects/x/model/x.mdl",
                 "expected": 1, "actual": 2},
            ]),
            make_issue("LAYOUT_UNLISTED_FILE", ["readme.md"]),
        ])

        mismatch = issues[0]
        self.assertEqual(mismatch["impact"], "potentially_runtime")
        self.assertEqual(
            mismatch["classified_files"][0]["path"],
            "SimObjects/x/model/x.mdl",
        )

        unlisted = issues[1]
        self.assertEqual(unlisted["impact"], "likely_non_runtime")

    def test_non_file_rules_stay_unknown(self):
        issues = self._run([
            make_issue("MANIFEST_MISSING_TITLE", []),
            make_issue("LAYOUT_MISSING", []),
        ])

        for issue in issues:
            self.assertEqual(issue["impact"], "unknown")
            self.assertNotIn("classified_files", issue)

    def test_file_rule_without_details_is_unknown(self):
        issues = self._run([make_issue("LAYOUT_FILE_MISSING", [])])
        self.assertEqual(issues[0]["impact"], "unknown")
        self.assertEqual(issues[0]["classified_files"], [])


class ClassifierIntegrationTest(unittest.TestCase):
    """端到端：Analyzer 输出完整明细 → Classifier 全量分类。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.community = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_full_pipeline_missing_classification(self):
        # 前 11 个缺失的是文档，最后一个才是运行时资源。
        entries = [
            {"path": f"docs/guide_{i:02d}.md", "size": 1}
            for i in range(11)
        ]
        entries.append({"path": "panel.bgl", "size": 10})
        entries.append({"path": "readme.md", "size": 10})

        make_addon(self.community, "pipeline", layout_content=entries)

        addons, _ = scan_community(self.community)
        issues, _ = analyze_community_with_stats(
            addons, full_scan=True
        )
        issues = classify_issues(issues)

        missing = next(
            issue for issue in issues
            if issue["rule_id"] == "LAYOUT_FILE_MISSING"
        )
        self.assertEqual(missing["affected_count"], 13)
        self.assertEqual(missing["impact"], "potentially_runtime")
        self.assertEqual(len(missing["classified_files"]), 13)


if __name__ == "__main__":
    unittest.main()
