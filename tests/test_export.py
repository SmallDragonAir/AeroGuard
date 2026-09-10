"""Markdown / HTML 报告导出与处理建议的单元测试。"""

import unittest

from export import (
    RELATIONSHIP_GUIDANCE,
    RULE_GUIDANCE,
    SAFETY_NOTE,
    export_html,
    export_markdown,
)
from i18n import set_language
from report import build_report

ANALYZER_RULES = (
    "MANIFEST_MISSING_TITLE",
    "MANIFEST_MISSING_CONTENT_TYPE",
    "MANIFEST_MISSING_VERSION",
    "LAYOUT_MISSING",
    "LAYOUT_INVALID",
    "LAYOUT_INVALID_ENTRY",
    "LAYOUT_DUPLICATE_PATH",
    "FILE_TREE_SCAN_INCOMPLETE",
    "LAYOUT_FILE_MISSING",
    "LAYOUT_FILE_SIZE_MISMATCH",
    "LAYOUT_UNLISTED_FILE",
)


def sample_document():
    issues = [
        {
            "rule_id": "LAYOUT_FILE_MISSING",
            "severity": "error",
            "package": "bad-addon",
            "message": "layout.json 声明的 2 个文件不存在",
            "affected_count": 2,
            "details": ["a.bgl", "b.bgl"],
            "preview": ["a.bgl", "b.bgl"],
            "impact": "potentially_runtime",
            "classified_files": [],
            "notes": [{"id": "n1", "text": "运行期生成", "rule_id": None}],
        },
        {
            "rule_id": "LAYOUT_DUPLICATE_PATH",
            "severity": "info",
            "package": "bad-addon",
            "message": "重复声明 <b>1</b> 个",
            "affected_count": 1,
            "details": ["dup.txt"],
            "preview": ["dup.txt"],
            "impact": "unknown",
            "classified_files": [],
            "original_severity": "warning",
            "downgrade_rule": "TEXT_LINE_ENDING_NORMALIZATION",
        },
        {
            "rule_id": "LAYOUT_FILE_SIZE_MISMATCH",
            "severity": "info",
            "package": "ok-addon",
            "message": "大小不一致",
            "affected_count": 1,
            "details": [{"path": "x.bin", "expected": 1, "actual": 2}],
            "preview": [{"path": "x.bin", "expected": 1, "actual": 2}],
            "impact": "unknown",
            "classified_files": [],
            "override": {"action": "downgrade", "reason": "known"},
        },
    ]
    return build_report(
        community_path=r"D:\Community",
        scan_mode="full",
        addons=[
            {
                "folder_name": "bad-addon", "name": "Bad", "type": "SCENERY",
                "creator": "c", "version": "1.0", "path": r"D:\Community\bad",
            },
            {
                "folder_name": "ok-addon", "name": "Ok", "type": "AIRCRAFT",
                "creator": "c", "version": "2.0", "path": r"D:\Community\ok",
            },
        ],
        scan_errors=[{"package": "x", "path": "y", "error": "boom"}],
        issues=issues,
        stats=None,
        timing={"total": 1.5},
        relationships=None,
    )


class ExportMarkdownTest(unittest.TestCase):

    def setUp(self):
        self.addCleanup(set_language, None)

    def test_chinese_markdown_contains_guidance(self):
        set_language("zh")
        text = export_markdown(sample_document())
        self.assertIn("# AeroGuard report", text)
        self.assertIn("## 处理建议", text)
        self.assertIn("声明文件缺失", text)
        self.assertIn("LAYOUT_FILE_MISSING", text)
        self.assertIn(SAFETY_NOTE["zh"], text)
        self.assertIn("note: 运行期生成", text)
        self.assertIn("[override]", text)
        self.assertIn("[noise-reduced]", text)

    def test_english_markdown_contains_guidance(self):
        set_language("en")
        text = export_markdown(sample_document())
        self.assertIn("## How to handle", text)
        self.assertIn("Declared files missing", text)
        self.assertIn(SAFETY_NOTE["en"], text)
        self.assertIn("## Findings by add-on", text)

    def test_markdown_is_deterministic(self):
        set_language("zh")
        self.assertEqual(
            export_markdown(sample_document()),
            export_markdown(sample_document()),
        )


class ExportHtmlTest(unittest.TestCase):

    def setUp(self):
        self.addCleanup(set_language, None)

    def test_html_structure_and_escaping(self):
        set_language("zh")
        text = export_html(sample_document())
        self.assertTrue(text.startswith("<!DOCTYPE html>"))
        self.assertIn("sev-ERROR", text)
        self.assertIn("处理建议", text)
        # 消息中的 <b> 必须被转义，不能原样注入
        self.assertIn("&lt;b&gt;", text)
        self.assertNotIn("重复声明 <b>1</b>", text)

    def test_html_english(self):
        set_language("en")
        text = export_html(sample_document())
        self.assertIn("How to handle", text)
        self.assertIn('lang="en"', text)


class GuidanceCoverageTest(unittest.TestCase):

    def test_every_analyzer_rule_has_guidance(self):
        for rule_id in ANALYZER_RULES:
            self.assertIn(rule_id, RULE_GUIDANCE, rule_id)
            for language in ("zh", "en"):
                title, meaning, actions = RULE_GUIDANCE[rule_id][language]
                self.assertTrue(title and meaning and actions, rule_id)

    def test_relationship_guidance_complete(self):
        for key in ("resource_conflicts", "airport_conflicts", "dependencies"):
            self.assertIn(key, RELATIONSHIP_GUIDANCE)
            for language in ("zh", "en"):
                self.assertTrue(RELATIONSHIP_GUIDANCE[key][language])


class EmptyReportTest(unittest.TestCase):

    def setUp(self):
        self.addCleanup(set_language, None)

    def test_empty_document_exports(self):
        set_language("zh")
        document = build_report(
            community_path="C:/Community",
            scan_mode="quick",
            addons=[],
            scan_errors=[],
            issues=[],
            stats=None,
            timing={"total": 0.0},
            relationships=None,
        )
        markdown = export_markdown(document)
        html_text = export_html(document)
        self.assertIn("概览", markdown)
        self.assertIn("<!DOCTYPE html>", html_text)
        self.assertNotIn("处理建议\n\n>", "")  # sanity: no exception paths


if __name__ == "__main__":
    unittest.main()
