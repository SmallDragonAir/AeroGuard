"""i18n 语言解析与目录查找的单元测试。"""

import unittest
from unittest import mock

from i18n import (
    current_language,
    localize_document,
    localize_text,
    resolve_language,
    set_language,
    tr,
)


class ResolveLanguageTest(unittest.TestCase):

    def tearDown(self):
        set_language(None)

    def test_override_wins_over_env(self):
        with mock.patch.dict("os.environ", {"AEROGUARD_LANG": "zh"}):
            self.assertEqual(resolve_language("en"), "en")
            self.assertEqual(resolve_language("zh-CN"), "zh")
            self.assertEqual(resolve_language("en-US"), "en")

    def test_env_variants(self):
        with mock.patch.dict("os.environ", {"AEROGUARD_LANG": "zh-CN"}):
            self.assertEqual(resolve_language(), "zh")
        with mock.patch.dict("os.environ", {"AEROGUARD_LANG": "en"}):
            self.assertEqual(resolve_language(), "en")


class TranslateTest(unittest.TestCase):

    def tearDown(self):
        set_language(None)

    def test_zh_default_returns_catalog_text(self):
        set_language("zh")
        self.assertEqual(
            tr("issue.layout.missing"), "缺少 layout.json"
        )
        self.assertEqual(tr("gui.head.severity"), "等级")

    def test_english_returns_english(self):
        set_language("en")
        self.assertEqual(
            tr("issue.layout.missing"), "layout.json is missing"
        )
        self.assertEqual(tr("gui.head.severity"), "Severity")

    def test_placeholders_are_formatted(self):
        set_language("en")
        self.assertEqual(
            tr("issue.file.missing", n=3),
            "3 file(s) declared in layout.json do not exist",
        )
        set_language("zh")
        self.assertEqual(
            tr("issue.file.size_mismatch", n=2),
            "发现 2 个文件大小与 layout.json 不一致",
        )

    def test_missing_key_falls_back_without_crash(self):
        set_language("en")
        self.assertEqual(tr("no.such.key"), "no.such.key")


class LocalizeTextTest(unittest.TestCase):

    def setUp(self):
        set_language("en")
        self.addCleanup(set_language, None)

    def test_management_templates(self):
        self.assertEqual(
            localize_text("ZIP 包含不安全路径：../evil.txt"),
            "ZIP contains an unsafe path: ../evil.txt",
        )
        self.assertEqual(
            localize_text("未找到包：my-addon"),
            "Package not found: my-addon",
        )
        self.assertEqual(
            localize_text("Profile 已存在：C:\\x.json；使用 --replace 显式更新"),
            "Profile already exists: C:\\x.json; use --replace to update "
            "explicitly",
        )

    def test_history_and_notes_templates(self):
        self.assertEqual(
            localize_text("扫描模式不同，文件一致性问题变化不可直接比较"),
            "Scan modes differ; file-consistency changes cannot be compared "
            "directly",
        )
        self.assertEqual(
            localize_text("未找到结论记录：20260101T000000Z-abc"),
            "Knowledge record not found: 20260101T000000Z-abc",
        )
        self.assertEqual(
            localize_text("同一 (包, 规则) 已有覆盖：alpha / X_RULE"),
            "An override already exists for (package, rule): "
            "alpha / X_RULE",
        )

    def test_unknown_text_unchanged(self):
        self.assertEqual(localize_text("not a known message"), "not a known message")

    def test_zh_language_is_noop(self):
        set_language("zh")
        self.assertEqual(
            localize_text("未找到包：alpha"), "未找到包：alpha"
        )

    def test_localize_document_walks_structures(self):
        document = {
            "warnings": [
                {"warning": "Profile 中的包当前未安装"},
            ],
            "count": 1,
        }
        localized = localize_document(document)
        self.assertEqual(
            localized["warnings"][0]["warning"],
            "The package in this Profile is not currently installed",
        )
        self.assertEqual(localized["count"], 1)

    def test_cli_keys(self):
        self.assertEqual(
            tr("cli.manage_failed", error="boom"), "Management failed: boom"
        )
        self.assertEqual(
            tr("cli.compare_no_diff"), "no changes"
        )


if __name__ == "__main__":
    unittest.main()
