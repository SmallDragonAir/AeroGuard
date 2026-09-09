import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from management import AddonManager, ManagementError

from .fixtures import make_addon


class AddonManagerTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.community = self.root / "Community"
        self.community.mkdir()
        self.state = self.root / "state"
        self.manager = AddonManager(self.community, self.state)
        self.addCleanup(self._tmp.cleanup)

    def _make_clean_addon(self, root, name, version="1.0", extra_files=None):
        files = {"SimObjects/Test/panel.cfg": b"x"}
        files.update(extra_files or {})
        layout = [
            {"path": path, "size": len(content)}
            for path, content in files.items()
        ]
        return make_addon(
            root,
            name,
            manifest={"package_version": version},
            layout_content=layout,
            files=files,
        )

    def test_disable_and_enable_round_trip(self):
        self._make_clean_addon(self.community, "alpha")

        disabled = self.manager.disable("ALPHA")
        inventory = self.manager.inventory()

        self.assertEqual(disabled["kind"], "disable")
        self.assertEqual(inventory["summary"]["enabled"], 0)
        self.assertEqual(inventory["disabled"][0]["package"], "alpha")

        enabled = self.manager.enable("alpha")

        self.assertEqual(enabled["kind"], "enable")
        self.assertTrue((self.community / "alpha" / "manifest.json").is_file())

    def test_disable_reports_active_declared_dependents(self):
        self._make_clean_addon(self.community, "base")
        dependent = self._make_clean_addon(self.community, "dependent")
        manifest_path = dependent / "manifest.json"
        manifest = json.loads(manifest_path.read_text("utf-8"))
        manifest["dependencies"] = [{"name": "base", "package_version": "1"}]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = self.manager.disable("base")

        self.assertEqual(result["dependency_warnings"], [{
            "package": "dependent",
            "dependency": "base",
            "warning": "启用包声明依赖即将离开 Community 的包",
        }])

    def test_profile_restores_recorded_states_and_leaves_new_package(self):
        self._make_clean_addon(self.community, "alpha")
        self._make_clean_addon(self.community, "beta")
        self.manager.disable("beta")
        self.manager.save_profile("mixed")

        self.manager.disable("alpha")
        self.manager.enable("beta")
        self._make_clean_addon(self.community, "later")
        dry_run = self.manager.apply_profile("mixed", dry_run=True)

        self.assertEqual(len(dry_run["moves"]), 2)
        self.assertTrue((self.community / "later").is_dir())

        result = self.manager.apply_profile("mixed")

        self.assertEqual(result["kind"], "apply_profile")
        self.assertTrue((self.community / "alpha").is_dir())
        self.assertTrue((self.state / "disabled" / "beta").is_dir())
        self.assertTrue((self.community / "later").is_dir())

    def test_quarantine_restores_previous_disabled_state(self):
        self._make_clean_addon(self.community, "alpha")
        self.manager.disable("alpha")

        self.manager.quarantine("alpha", "test reason")
        metadata = json.loads(
            (self.state / "quarantine" / "alpha.json").read_text("utf-8")
        )

        self.assertEqual(metadata["previous_status"], "disabled")
        self.assertEqual(metadata["reason"], "test reason")

        self.manager.restore_quarantine("alpha")

        self.assertTrue((self.state / "disabled" / "alpha").is_dir())
        self.assertFalse((self.state / "quarantine" / "alpha.json").exists())

    def test_clean_directory_passes_preinstall_inspection(self):
        source = self.root / "source"
        self._make_clean_addon(source, "alpha")

        inspection = self.manager.inspect_install_source(source)

        self.assertTrue(inspection.can_install)
        self.assertEqual(inspection.summary()["packages"], 1)
        self.assertEqual(inspection.executable_files, [])

    def test_zip_path_traversal_is_rejected(self):
        archive = self.root / "unsafe.zip"
        with zipfile.ZipFile(archive, "w") as file:
            file.writestr("../outside.txt", "bad")

        inspection = self.manager.inspect_install_source(archive)

        self.assertFalse(inspection.can_install)
        self.assertIn("不安全路径", inspection.errors[0]["error"])
        self.assertFalse((self.root / "outside.txt").exists())

    def test_executable_requires_explicit_install_override(self):
        source = self.root / "source"
        self._make_clean_addon(
            source,
            "alpha",
            extra_files={"tools/setup.exe": b"MZ"},
        )

        inspection = self.manager.inspect_install_source(source)

        self.assertTrue(inspection.can_install)
        self.assertTrue(inspection.requires_executable_override)
        self.assertFalse(inspection.summary()["ready_for_default_install"])
        with self.assertRaisesRegex(ManagementError, "allow-executables"):
            self.manager.install(source)

        result = self.manager.install(source, allow_executables=True)

        self.assertEqual(result["transaction"]["status"], "committed")
        self.assertTrue((self.community / "alpha" / "tools/setup.exe").is_file())

    def test_replacing_package_then_rollback_restores_old_version(self):
        old = self._make_clean_addon(self.community, "alpha", version="1.0")
        (old / "marker.txt").write_text("old", encoding="utf-8")
        source = self.root / "source"
        new = self._make_clean_addon(source, "alpha", version="2.0")
        (new / "marker.txt").write_text("new", encoding="utf-8")

        result = self.manager.install(source)
        transaction = result["transaction"]

        active_manifest = json.loads(
            (self.community / "alpha" / "manifest.json").read_text("utf-8")
        )
        self.assertEqual(active_manifest["package_version"], "2.0")
        self.assertEqual(
            (self.community / "alpha" / "marker.txt").read_text("utf-8"),
            "new",
        )

        rolled_back = self.manager.rollback_install(transaction["id"])

        restored_manifest = json.loads(
            (self.community / "alpha" / "manifest.json").read_text("utf-8")
        )
        self.assertEqual(rolled_back["status"], "rolled_back")
        self.assertEqual(restored_manifest["package_version"], "1.0")
        self.assertEqual(
            (self.community / "alpha" / "marker.txt").read_text("utf-8"),
            "old",
        )
        self.assertTrue(
            (self.state / "rolled-back" / transaction["id"] / "alpha").is_dir()
        )

    def test_rollback_refuses_changed_installed_metadata(self):
        source = self.root / "source"
        self._make_clean_addon(source, "alpha", version="2.0")
        transaction = self.manager.install(source)["transaction"]
        manifest_path = self.community / "alpha" / "manifest.json"
        manifest = json.loads(manifest_path.read_text("utf-8"))
        manifest["package_version"] = "2.1"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaisesRegex(ManagementError, "已变化"):
            self.manager.rollback_install(transaction["id"])

        self.assertTrue((self.community / "alpha").is_dir())

    def test_versions_include_disabled_and_archived_versions(self):
        self._make_clean_addon(self.community, "alpha", version="1.0")
        source = self.root / "source"
        self._make_clean_addon(source, "alpha", version="2.0")
        self.manager.install(source)
        self.manager.disable("alpha")

        versions = self.manager.versions()

        self.assertEqual(versions["summary"]["current_versions"], 1)
        self.assertEqual(versions["summary"]["archived_versions"], 1)
        self.assertEqual(versions["current"][0]["version"], "2.0")
        self.assertEqual(versions["archived"][0]["version"], "1.0")

    def test_profile_requires_explicit_replace(self):
        self._make_clean_addon(self.community, "alpha")
        self.manager.save_profile("daily")

        with self.assertRaisesRegex(ManagementError, "--replace"):
            self.manager.save_profile("daily")

        updated = self.manager.save_profile("daily", replace=True)
        self.assertEqual(updated["name"], "daily")

    def test_inventory_surfaces_invalid_directory_and_profile_skips_it(self):
        invalid = self.community / "not-a-package"
        invalid.mkdir()

        inventory = self.manager.inventory()
        profile = self.manager.save_profile("valid-only")

        self.assertEqual(inventory["summary"]["invalid_entries"], 1)
        self.assertIn("error", inventory["enabled"][0])
        self.assertEqual(profile["packages"], {})
        self.assertEqual(profile["skipped_entries"][0]["package"],
                         "not-a-package")


if __name__ == "__main__":
    unittest.main()
