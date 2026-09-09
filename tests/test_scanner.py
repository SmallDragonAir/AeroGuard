import tempfile
import unittest
from pathlib import Path

from .fixtures import make_addon
from scanner import scan_community


class ScannerTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.community = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_empty_community(self):
        addons, scan_errors = scan_community(self.community)
        self.assertEqual(addons, [])
        self.assertEqual(scan_errors, [])

    def test_finds_manifest_addons_and_fields(self):
        make_addon(self.community, "addon-a")
        make_addon(self.community, "addon-b")

        addons, scan_errors = scan_community(self.community)

        self.assertEqual(scan_errors, [])
        self.assertEqual(len(addons), 2)

        names = {addon["folder_name"] for addon in addons}
        self.assertEqual(names, {"addon-a", "addon-b"})

        addon = next(a for a in addons if a["folder_name"] == "addon-a")
        self.assertEqual(addon["name"], "Test Addon")
        self.assertEqual(addon["type"], "AIRCRAFT")
        self.assertEqual(addon["creator"], "fixture")
        self.assertEqual(addon["version"], "1.0.0")
        self.assertTrue(Path(addon["path"]).is_dir())

    def test_keeps_raw_manifest(self):
        make_addon(
            self.community,
            "addon-a",
            manifest={"title": "T", "dependencies": ["core-lib"]},
        )
        addons, _ = scan_community(self.community)

        manifest = addons[0]["manifest"]
        self.assertEqual(manifest["title"], "T")
        self.assertEqual(manifest["dependencies"], ["core-lib"])
        self.assertEqual(manifest["content_type"], "AIRCRAFT")

    def test_ignores_dirs_without_manifest(self):
        make_addon(self.community, "real-addon")
        (self.community / "no-manifest").mkdir()

        addons, _ = scan_community(self.community)
        self.assertEqual(len(addons), 1)
        self.assertEqual(addons[0]["folder_name"], "real-addon")

    def test_ignores_plain_files(self):
        make_addon(self.community, "real-addon")
        (self.community / "notes.txt").write_text("hi", encoding="utf-8")

        addons, _ = scan_community(self.community)
        self.assertEqual(len(addons), 1)

    def test_broken_manifest_reports_error(self):
        target = make_addon(self.community, "broken-addon")
        target.joinpath("manifest.json").write_text(
            "{ not valid json", encoding="utf-8"
        )

        addons, scan_errors = scan_community(self.community)

        self.assertEqual(addons, [])
        self.assertEqual(len(scan_errors), 1)
        self.assertEqual(scan_errors[0]["package"], "broken-addon")
        self.assertEqual(Path(scan_errors[0]["path"]), target)
        self.assertIn("error", scan_errors[0])

    def test_non_object_manifest_reports_error_and_scan_continues(self):
        broken = make_addon(self.community, "broken-root")
        broken.joinpath("manifest.json").write_text(
            "[]", encoding="utf-8"
        )
        make_addon(self.community, "healthy")

        addons, scan_errors = scan_community(self.community)

        self.assertEqual([addon["folder_name"] for addon in addons],
                         ["healthy"])
        self.assertEqual(len(scan_errors), 1)
        self.assertEqual(scan_errors[0]["package"], "broken-root")
        self.assertIn("顶层必须是 JSON 对象", scan_errors[0]["error"])

    def test_missing_title_is_none_not_crash(self):
        make_addon(self.community, "no-title", manifest={"title": None})

        addons, scan_errors = scan_community(self.community)
        self.assertEqual(scan_errors, [])
        self.assertIsNone(addons[0]["name"])


if __name__ == "__main__":
    unittest.main()
