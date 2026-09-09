import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analyzer import build_file_index


def _try_junction(link, target):
    """尝试创建 Windows 目录联接（junction），失败返回 False。"""
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.returncode == 0
    except (OSError, ValueError):
        return False


class FileIndexTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _keys(self, index):
        return set(index.keys())

    def test_basic_index_normalizes_paths(self):
        (self.root / "a" / "b").mkdir(parents=True)
        (self.root / "a" / "b" / "File.TXT").write_bytes(b"x" * 3)
        (self.root / "c.txt").write_bytes(b"y" * 5)

        index = build_file_index(self.root)

        self.assertEqual(self._keys(index), {
            "a/b/file.txt",
            "c.txt",
        })
        self.assertEqual(index["c.txt"]["size"], 5)
        self.assertEqual(index["a/b/file.txt"]["path"], "a/b/File.TXT")

    def test_junction_dirs_followed(self):
        (self.root / "real").mkdir()
        (self.root / "real" / "f.txt").write_bytes(b"data")
        link = self.root / "reallink"

        if not _try_junction(link, self.root / "real"):
            self.skipTest("无法创建 junction，跳过")

        index = build_file_index(self.root)

        # 真实目录与联接指向的目录都会以各自的逻辑路径出现。
        self.assertIn("real/f.txt", index)
        self.assertIn("reallink/f.txt", index)
        self.assertEqual(
            index["reallink/f.txt"]["size"], 4
        )

    def test_junction_self_loop_terminates(self):
        (self.root / "top.txt").write_bytes(b"t")
        link = self.root / "loop"

        if not _try_junction(link, self.root):
            self.skipTest("无法创建 junction，跳过")

        # 若循环防护失效，这里会递归直至崩溃或超时。
        index = build_file_index(self.root)

        self.assertIn("top.txt", index)
        self.assertNotIn("loop/top.txt", index)

    def test_missing_directory_is_empty(self):
        index = build_file_index(self.root / "does-not-exist")
        self.assertEqual(index, {})

    def test_normal_directories_do_not_repeat_realpath_resolution(self):
        (self.root / "a" / "b" / "c").mkdir(parents=True)
        (self.root / "a" / "b" / "c" / "f.txt").write_bytes(b"x")
        real_realpath = os.path.realpath

        with patch("analyzer.os.path.realpath", wraps=real_realpath) as mocked:
            index = build_file_index(self.root)

        self.assertIn("a/b/c/f.txt", index)
        self.assertEqual(mocked.call_count, 1)


if __name__ == "__main__":
    unittest.main()
