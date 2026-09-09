"""三个 CLI 的 argparse 契约测试（只解析参数，不执行任何操作）。

覆盖 subcommand 分发、标志位与必填项，防止参数接口回归。
"""

import contextlib
import io
import unittest
from unittest import mock

import main as main_cli
import manage as manage_cli
import history_cli


class MainParserTest(unittest.TestCase):

    def test_positional_path_and_mode(self):
        args = main_cli.parse_args(
            ["D:/Community", "--mode", "full"]
        )
        self.assertEqual(args.community_path, "D:/Community")
        self.assertEqual(args.mode, "full")
        self.assertIsNone(args.json)

    def test_json_default_path_variant(self):
        args = main_cli.parse_args(
            ["D:/Community", "--mode", "quick", "--json"]
        )
        self.assertEqual(args.json, "")

    def test_json_explicit_path(self):
        args = main_cli.parse_args(
            ["D:/Community", "--json", "out/scan.json"]
        )
        self.assertEqual(args.json, "out/scan.json")

    def test_no_relationships_flag(self):
        args = main_cli.parse_args(
            ["D:/Community", "--mode", "quick", "--no-relationships"]
        )
        self.assertTrue(args.no_relationships)
        self.assertFalse(
            main_cli.parse_args(["D:/Community"]).no_relationships
        )

    def test_invalid_mode_rejected(self):
        with self.assertRaises(SystemExit):
            main_cli.parse_args(["D:/Community", "--mode", "turbo"])

    def test_eof_without_path_returns_usage_exit(self):
        # 非交互环境（stdin 已关闭）下缺省路径不应以 traceback 崩溃。
        with mock.patch("builtins.input", side_effect=EOFError):
            with contextlib.redirect_stdout(io.StringIO()):
                code = main_cli.main(["--mode", "quick"])
        self.assertEqual(code, 2)

    def test_path_argument_skips_prompting(self):
        # 提供路径且提供模式时不应触发 input()
        with mock.patch("builtins.input", side_effect=AssertionError("不应提示")):
            with contextlib.redirect_stdout(io.StringIO()):
                code = main_cli.main(["D:/not-a-real-community", "--mode", "quick"])
        # 路径不存在 → 提前返回 1，说明流程未进入交互输入
        self.assertEqual(code, 1)


class ManageParserTest(unittest.TestCase):

    def _parse(self, argv):
        return manage_cli._build_parser().parse_args(argv)

    def test_inventory(self):
        args = self._parse(["C:/Community", "inventory"])
        self.assertEqual(args.command, "inventory")

    def test_state_dir_position(self):
        args = self._parse(
            ["C:/Community", "--state-dir", "D:/state", "disable", "pkg"]
        )
        self.assertEqual(args.command, "disable")
        self.assertEqual(args.package, "pkg")
        self.assertEqual(args.state_dir, "D:/state")

    def test_quarantine_default_reason(self):
        args = self._parse(["C:/Community", "quarantine", "pkg"])
        self.assertEqual(args.command, "quarantine")
        self.assertEqual(args.reason, "manual quarantine")

    def test_profile_apply_dry_run(self):
        args = self._parse(
            ["C:/Community", "profile-apply", "flying", "--dry-run"]
        )
        self.assertTrue(args.dry_run)

    def test_install_executables_flag(self):
        args = self._parse(
            ["C:/Community", "install", "a.zip", "--allow-executables"]
        )
        self.assertTrue(args.allow_executables)

    def test_check_and_rollback(self):
        args = self._parse(["C:/Community", "check", "a.zip"])
        self.assertEqual(args.command, "check")
        self.assertEqual(args.source, "a.zip")

        args = self._parse(["C:/Community", "rollback", "txn-1"])
        self.assertEqual(args.command, "rollback")
        self.assertEqual(args.transaction_id, "txn-1")

    def test_note_commands(self):
        args = self._parse(["C:/Community", "note-list"])
        self.assertEqual(args.command, "note-list")
        self.assertIsNone(args.package)

        args = self._parse(
            ["C:/Community", "note-list", "alpha"]
        )
        self.assertEqual(args.package, "alpha")

        args = self._parse(
            ["C:/Community", "note-add", "alpha",
             "--text", "已知结论", "--rule", "LAYOUT_FILE_MISSING"]
        )
        self.assertEqual(args.command, "note-add")
        self.assertEqual(args.rule, "LAYOUT_FILE_MISSING")

        args = self._parse(["C:/Community", "note-remove", "n-1"])
        self.assertEqual(args.command, "note-remove")
        self.assertEqual(args.note_id, "n-1")

    def test_note_add_requires_text(self):
        with self.assertRaises(SystemExit):
            self._parse(["C:/Community", "note-add", "alpha"])

    def test_missing_command_rejected(self):
        with self.assertRaises(SystemExit):
            self._parse(["C:/Community"])


class HistoryCliParserTest(unittest.TestCase):

    def _parse(self, argv):
        return history_cli._build_parser().parse_args(argv)

    def test_record_defaults_to_quick(self):
        args = self._parse(["C:/Community", "record"])
        self.assertEqual(args.command, "record")
        self.assertEqual(args.mode, "quick")
        self.assertIsNone(args.label)

    def test_record_full_with_label(self):
        args = self._parse(
            ["C:/Community", "record", "--mode", "full", "--label", "SU4"]
        )
        self.assertEqual(args.mode, "full")
        self.assertEqual(args.label, "SU4")

    def test_list_limit(self):
        args = self._parse(["C:/Community", "list", "--limit", "5"])
        self.assertEqual(args.command, "list")
        self.assertEqual(args.limit, 5)

    def test_baseline_set_with_replace(self):
        args = self._parse(
            ["C:/Community", "baseline-set", "stable",
             "--snapshot", "S1", "--replace"]
        )
        self.assertTrue(args.replace)
        self.assertEqual(args.snapshot, "S1")

    def test_compare_with_record_and_label(self):
        args = self._parse(
            ["C:/Community", "compare", "stable",
             "--mode", "full", "--record", "--label", "after"]
        )
        self.assertEqual(args.command, "compare")
        self.assertTrue(args.record)
        self.assertEqual(args.label, "after")


class HistoryCliSummaryTest(unittest.TestCase):

    def test_compare_summary_counts_changes(self):
        comparison = {
            "baseline_name": "stable",
            "summary": {
                "total_changes": 4,
                "compatibility_warnings": 1,
                "sections": {
                    "packages": {"added": 1, "removed": 0, "changed": 0},
                    "issues": {"added": 0, "removed": 0, "changed": 2},
                    "scan_errors": {"added": 0, "removed": 0, "changed": 0},
                },
            },
        }
        text = history_cli._compare_summary(comparison)

        self.assertIn("共 4 项变化", text)
        self.assertIn("packages 1 项", text)
        self.assertIn("issues 2 项", text)
        self.assertNotIn("scan_errors", text)
        self.assertIn("兼容性提示 1 条", text)

    def test_compare_summary_empty_environment(self):
        comparison = {
            "baseline_name": "stable",
            "summary": {
                "total_changes": 0,
                "compatibility_warnings": 0,
                "sections": {
                    "packages": {"added": 0, "removed": 0, "changed": 0},
                },
            },
        }
        text = history_cli._compare_summary(comparison)
        self.assertIn("无差异", text)


if __name__ == "__main__":
    unittest.main()
