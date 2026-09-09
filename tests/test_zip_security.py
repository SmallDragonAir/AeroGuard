"""management._validated_zip_members 的安全分支单元测试。

使用伪造的归档对象直接驱动校验逻辑，无需构造真实 ZIP 文件，
即可锁定所有拒绝分支，防止未来改动引入 zip-slip 等回归。
"""

import stat
import types
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from management import (
    MAX_ZIP_UNCOMPRESSED_BYTES,
    ManagementError,
    _safe_extract_zip,
    _validated_zip_members,
)


def fake_info(filename, *, file_size=1, flag_bits=0, external_attr=0):
    return types.SimpleNamespace(
        filename=filename,
        file_size=file_size,
        flag_bits=flag_bits,
        external_attr=external_attr,
    )


def fake_archive(*infos):
    return types.SimpleNamespace(infolist=lambda: list(infos))


class ZipValidationBranchesTest(unittest.TestCase):

    def _expect_reject(self, *infos):
        with self.assertRaises(ManagementError):
            _validated_zip_members(fake_archive(*infos))

    def _accept(self, *infos):
        members = _validated_zip_members(fake_archive(*infos))
        self.assertEqual(len(members), len(infos))
        return members

    def test_absolute_path_rejected(self):
        self._expect_reject(fake_info("/etc/passwd"))

    def test_windows_drive_path_rejected(self):
        self._expect_reject(fake_info("C:/secret.txt"))
        self._expect_reject(fake_info("C:secret.txt"))

    def test_traversal_rejected(self):
        self._expect_reject(fake_info("../evil.txt"))
        self._expect_reject(fake_info("pkg/../../evil.txt"))
        # 注意："./evil.txt" 会被 PurePosixPath 归一化为 "evil.txt"，
        # 解压仍落在目标目录内，本身不构成逃逸，因此这里不期望拒绝。

    def test_windows_illegal_characters_rejected(self):
        self._expect_reject(fake_info("pkg/na<me.txt"))
        self._expect_reject(fake_info('pkg/na"me.txt'))
        self._expect_reject(fake_info("pkg/na?me.txt"))
        self._expect_reject(fake_info("pkg/na*me.txt"))
        self._expect_reject(fake_info("pkg/na|me.txt"))

    def test_trailing_space_or_dot_component_rejected(self):
        self._expect_reject(fake_info("pkg/name.txt "))
        self._expect_reject(fake_info("pkg/name."))

    def test_encrypted_entry_rejected(self):
        self._expect_reject(fake_info("a.txt", flag_bits=0x1))

    def test_symlink_entry_rejected(self):
        mode = stat.S_IFLNK | 0o777
        self._expect_reject(
            fake_info("a.txt", external_attr=mode << 16)
        )

    def test_regular_file_accepted(self):
        members = self._accept(fake_info("pkg/a.txt"))
        self.assertEqual(members[0][1].as_posix(), "pkg/a.txt")

    def test_casefold_duplicate_rejected(self):
        self._expect_reject(
            fake_info("pkg/a.txt"),
            fake_info("pkg/A.TXT"),
        )

    def test_total_uncompressed_size_over_limit_rejected(self):
        # 100 GiB 上限按地板除法取整会少 1 字节，
        # 因此第三个条目需要比 one 大 2 才能确实超过上限。
        one = MAX_ZIP_UNCOMPRESSED_BYTES // 3
        self._expect_reject(
            fake_info("a.bin", file_size=one),
            fake_info("b.bin", file_size=one),
            fake_info("c.bin", file_size=one + 2),
        )


class ZipRealArchiveTest(unittest.TestCase):

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self._tmp.name) / "out"
        self.addCleanup(self._tmp.cleanup)

    def _write_zip(self, names):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name in names:
                archive.writestr(name, b"content")
        return buffer.getvalue()

    def test_casefold_duplicate_members_rejected_when_extracting(self):
        data = self._write_zip(["pkg/a.txt", "pkg/A.TXT"])
        source = Path(self._tmp.name) / "dup.zip"
        source.write_bytes(data)

        with self.assertRaises(ManagementError):
            _safe_extract_zip(source, self.dest)

    def test_traversal_member_rejected_when_extracting(self):
        data = self._write_zip(["../escape.txt"])
        source = Path(self._tmp.name) / "bad.zip"
        source.write_bytes(data)

        with self.assertRaises(ManagementError):
            _safe_extract_zip(source, self.dest)

    def test_clean_archive_extracts_under_destination(self):
        data = self._write_zip(["pkg/a.txt", "pkg/sub/b.txt"])
        source = Path(self._tmp.name) / "ok.zip"
        source.write_bytes(data)

        _safe_extract_zip(source, self.dest)

        self.assertTrue((self.dest / "pkg" / "a.txt").is_file())
        self.assertTrue((self.dest / "pkg" / "sub" / "b.txt").is_file())
        # 临时根目录下除三个 zip 与解压目录外不应有逃逸产物
        leftover = [
            p.name for p in Path(self._tmp.name).iterdir()
            if p.name not in {"dup.zip", "bad.zip", "ok.zip", "out"}
        ]
        self.assertEqual(leftover, [])


if __name__ == "__main__":
    unittest.main()
