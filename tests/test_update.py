"""检查更新（update.py）的单元测试（全部使用注入的 fetch，不联网）。"""

import contextlib
import io
import unittest
from unittest import mock

import main as main_cli
from update import (
    RELEASES_PAGE,
    UpdateError,
    check_for_update,
    compare_versions,
    parse_version,
)


def fake_fetch(payload):
    def _fetch(url, timeout=None):
        return payload
    return _fetch


class VersionParsingTest(unittest.TestCase):

    def test_parse_variants(self):
        self.assertEqual(parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version("1.2"), (1, 2, 0))
        self.assertEqual(parse_version("2"), (2, 0, 0))
        self.assertEqual(parse_version("1.10.0-beta"), (1, 10, 0))
        self.assertEqual(parse_version(""), ())
        self.assertEqual(parse_version(None), ())

    def test_compare(self):
        self.assertEqual(compare_versions("1.2.0", "1.1.9"), 1)
        self.assertEqual(compare_versions("v1.2.0", "1.2.0"), 0)
        self.assertEqual(compare_versions("1.2.0", "1.10.0"), -1)
        self.assertEqual(compare_versions("bad", "1.0.0"), 0)


class CheckForUpdateTest(unittest.TestCase):

    def test_update_available(self):
        result = check_for_update(
            current="0.1.0",
            fetch=fake_fetch({
                "tag_name": "v0.2.0",
                "html_url": "https://example.test/release",
                "name": "0.2.0",
                "published_at": "2026-01-01T00:00:00Z",
                "body": "notes",
            }),
        )
        self.assertTrue(result["update_available"])
        self.assertEqual(result["latest_version"], "0.2.0")
        self.assertEqual(result["release_url"], "https://example.test/release")
        self.assertEqual(result["notes_excerpt"], "notes")
        self.assertFalse(result["downloaded"])

    def test_up_to_date(self):
        result = check_for_update(
            current="0.2.0",
            fetch=fake_fetch({"tag_name": "v0.2.0"}),
        )
        self.assertFalse(result["update_available"])
        # 缺少 html_url 时回退到发布页
        self.assertEqual(result["release_url"], RELEASES_PAGE)

    def test_invalid_tag_raises(self):
        with self.assertRaises(UpdateError):
            check_for_update(current="0.1.0", fetch=fake_fetch({}))
        with self.assertRaises(UpdateError):
            check_for_update(
                current="0.1.0", fetch=fake_fetch(["not", "a", "dict"])
            )

    def test_network_error_wrapped(self):
        def broken_fetch(url, timeout=None):
            raise OSError("connection reset")

        with self.assertRaises(UpdateError) as context:
            check_for_update(current="0.1.0", fetch=broken_fetch)
        self.assertIn("无法连接更新服务", str(context.exception))

    def test_notes_excerpt_trimmed(self):
        result = check_for_update(
            current="0.1.0",
            fetch=fake_fetch({"tag_name": "v9.9.9", "body": "x" * 5000}),
        )
        self.assertEqual(len(result["notes_excerpt"]), 600)

    def test_unparseable_tag_is_not_reported_as_current(self):
        # 真实场景：仓库 Release 的 tag 是 "AeroGuard" 这类非版本号
        result = check_for_update(
            current="0.1.0",
            fetch=fake_fetch({"tag_name": "AeroGuard"}),
        )
        self.assertFalse(result["version_comparable"])
        self.assertFalse(result["update_available"])
        self.assertEqual(result["tag"], "AeroGuard")

    def test_release_name_fallback(self):
        result = check_for_update(
            current="0.1.0",
            fetch=fake_fetch({
                "tag_name": "AeroGuard",
                "name": "v0.2.0",
                "html_url": "https://example.test/rel",
            }),
        )
        self.assertTrue(result["version_comparable"])
        self.assertTrue(result["update_available"])
        self.assertEqual(result["latest_version"], "0.2.0")


class UpdateCliTest(unittest.TestCase):

    def _run(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main_cli.run_update_check()
        return code, buffer.getvalue()

    def test_cli_reports_available(self):
        with mock.patch.object(
            main_cli, "check_for_update",
            return_value={
                "current_version": "0.1.0",
                "latest_version": "0.2.0",
                "update_available": True,
                "release_url": "https://example.test",
            },
        ):
            code, text = self._run()
        self.assertEqual(code, 0)
        self.assertIn("0.2.0", text)

    def test_cli_handles_failure(self):
        with mock.patch.object(
            main_cli, "check_for_update",
            side_effect=UpdateError("无法连接更新服务：boom"),
        ):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = main_cli.run_update_check()
        self.assertEqual(code, 2)

    def test_cli_reports_uncomparable(self):
        with mock.patch.object(
            main_cli, "check_for_update",
            return_value={
                "current_version": "0.1.0",
                "latest_version": "AeroGuard",
                "tag": "AeroGuard",
                "version_comparable": False,
                "update_available": False,
                "release_url": "https://example.test",
            },
        ):
            code, text = self._run()
        self.assertEqual(code, 0)
        self.assertIn("无法从更新信息比较版本", text)


if __name__ == "__main__":
    unittest.main()
