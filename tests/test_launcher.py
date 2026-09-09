"""launcher 的命令分发逻辑单元测试（不启动 GUI / 不执行 CLI）。"""

import unittest

from launcher import select_command


class LauncherSelectTest(unittest.TestCase):

    def test_no_args_defaults_to_gui(self):
        self.assertEqual(select_command([]), ("gui", []))

    def test_gui_aliases(self):
        for head in ("gui", "app"):
            self.assertEqual(select_command([head]), ("gui", []))

    def test_scan_route_keeps_remainder(self):
        self.assertEqual(
            select_command(["scan", "D:/C", "--mode", "full"]),
            ("scan", ["D:/C", "--mode", "full"]),
        )

    def test_manage_and_history_routes(self):
        self.assertEqual(
            select_command(["manage", "D:/C", "inventory"]),
            ("manage", ["D:/C", "inventory"]),
        )
        self.assertEqual(
            select_command(["history", "D:/C", "list"]),
            ("history", ["D:/C", "list"]),
        )

    def test_case_insensitive_command(self):
        self.assertEqual(select_command(["SCAN", "D:/C"]), ("scan", ["D:/C"]))

    def test_help_route(self):
        for head in ("-h", "--help", "help"):
            self.assertEqual(select_command([head]), ("help", []))

    def test_unknown_first_arg_falls_back_to_gui_with_args(self):
        # 兼容直接传路径的用法：AeroGuard.exe D:\Community --mode quick
        self.assertEqual(
            select_command(["D:/Community", "--mode", "quick"]),
            ("gui", ["D:/Community", "--mode", "quick"]),
        )


if __name__ == "__main__":
    unittest.main()
