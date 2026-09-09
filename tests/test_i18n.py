"""i18n 语言解析与目录查找的单元测试。"""

import unittest
from unittest import mock

from i18n import resolve_language, set_language, current_language, tr


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


if __name__ == "__main__":
    unittest.main()
