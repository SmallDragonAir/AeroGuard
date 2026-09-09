import tempfile
import unittest
from pathlib import Path

from .fixtures import make_addon
from relationships import analyze_relationships
from scanner import scan_community


class RelationshipAnalysisTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.community = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _analyze(self):
        addons, errors = scan_community(self.community)
        self.assertEqual(errors, [])
        return analyze_relationships(addons)

    def test_runtime_resource_overlap_with_different_sizes_is_warning(self):
        path = "SimObjects/Airplanes/Test/panel.cfg"
        make_addon(self.community, "alpha",
                   layout_content=[{"path": path, "size": 1}])
        make_addon(self.community, "beta",
                   layout_content=[{"path": path, "size": 2}])

        analysis = self._analyze()

        self.assertEqual(len(analysis.resource_conflicts), 1)
        conflict = analysis.resource_conflicts[0]
        self.assertEqual(conflict["severity"], "warning")
        self.assertEqual(conflict["scope"], "runtime_vfs")
        self.assertFalse(conflict["same_declared_size"])

    def test_missing_declared_size_is_not_treated_as_same_size(self):
        path = "Effects/shared.fx"
        make_addon(self.community, "alpha",
                   layout_content=[{"path": path, "size": 1}])
        make_addon(self.community, "beta",
                   layout_content=[{"path": path}])

        conflict = self._analyze().resource_conflicts[0]

        self.assertEqual(conflict["severity"], "warning")
        self.assertFalse(conflict["same_declared_size"])

    def test_dependency_marks_overlap_as_intentional(self):
        path = "SimObjects/Airplanes/Test/panel.cfg"
        make_addon(self.community, "base",
                   layout_content=[{"path": path, "size": 1}])
        make_addon(
            self.community,
            "patch",
            manifest={
                "dependencies": [{"name": "base", "package_version": "1"}]
            },
            layout_content=[{"path": path, "size": 2}],
        )

        conflict = self._analyze().resource_conflicts[0]

        self.assertEqual(conflict["severity"], "info")
        self.assertEqual(conflict["intentional_overrides"], [{
            "package": "patch",
            "target": "base",
            "basis": "declared_dependency",
        }])

    def test_unrelated_patch_hint_does_not_mark_resource_intentional(self):
        path = "Scenery/shared/index.bgl"
        make_addon(
            self.community,
            "unrelated-base",
            manifest={"package_order_hint": "CUSTOM_LOCAL_SCENERY"},
            layout_content=[{"path": path, "size": 1}],
        )
        make_addon(
            self.community,
            "unrelated-patch",
            manifest={"package_order_hint": "CUSTOM_LOCAL_SCENERY_PATCH"},
            layout_content=[{"path": path, "size": 2}],
        )

        conflict = self._analyze().resource_conflicts[0]

        self.assertEqual(conflict["severity"], "warning")
        self.assertEqual(conflict["intentional_overrides"], [])
        self.assertIsNone(conflict["likely_winner"])

    def test_global_override_marks_exact_path_as_intentional(self):
        path = "HTML_UI/shared.js"
        make_addon(self.community, "base",
                   layout_content=[{"path": path, "size": 1}])
        make_addon(
            self.community,
            "override",
            manifest={"globally_overriden_base_sim_files": [path]},
            layout_content=[{"path": path, "size": 2}],
        )

        conflict = self._analyze().resource_conflicts[0]

        self.assertEqual(conflict["severity"], "info")
        self.assertEqual(conflict["intentional_overrides"], [{
            "package": "override",
            "target": "base",
            "basis": "declared_global_override",
        }])

    def test_same_hint_reports_alphabetical_default_winner(self):
        path = "Effects/shared.fx"
        manifest = {"package_order_hint": "CUSTOM_VFX"}
        make_addon(self.community, "alpha", manifest=manifest,
                   layout_content=[{"path": path, "size": 1}])
        make_addon(self.community, "zulu", manifest=manifest,
                   layout_content=[{"path": path, "size": 1}])

        winner = self._analyze().resource_conflicts[0]["likely_winner"]

        self.assertEqual(winner["package"], "zulu")
        self.assertEqual(winner["confidence"], "default_order_only")

    def test_package_metadata_is_not_a_resource_conflict(self):
        entries = [{"path": "manifest.json", "size": 1}]
        make_addon(self.community, "alpha", layout_content=entries)
        make_addon(self.community, "beta", layout_content=entries)

        self.assertEqual(self._analyze().resource_conflicts, [])

    def test_airport_patch_is_identified_as_intentional_duplicate(self):
        path = "Scenery/vendor/ZHCC.bgl"
        make_addon(
            self.community,
            "vendor-airport-zhcc-main",
            manifest={
                "title": "ZHCC Main Airport",
                "content_type": "SCENERY",
                "package_order_hint": "CUSTOM_AIRPORT",
            },
            layout_content=[{"path": path, "size": 1}],
        )
        make_addon(
            self.community,
            "vendor-airport-zhcc-patch",
            manifest={
                "title": "ZHCC Airport Patch",
                "content_type": "SCENERY",
                "package_order_hint": "CUSTOM_AIRPORT_PATCH",
            },
            layout_content=[{"path": "Scenery/patch/ZHCC.bgl", "size": 2}],
        )

        analysis = self._analyze()

        self.assertEqual(len(analysis.airport_conflicts), 1)
        conflict = analysis.airport_conflicts[0]
        self.assertEqual(conflict["airport_code"], "ZHCC")
        self.assertEqual(conflict["severity"], "info")
        self.assertTrue(conflict["intentional_override"])
        self.assertEqual(
            conflict["likely_winner"], "vendor-airport-zhcc-patch"
        )

    def test_dependency_scope_and_cycles(self):
        make_addon(
            self.community,
            "alpha",
            manifest={"dependencies": [
                {"name": "beta", "package_version": "1"},
                {"name": "official-base", "package_version": "1"},
                "invalid",
            ]},
            layout_content=[],
        )
        make_addon(
            self.community,
            "beta",
            manifest={"dependencies": [
                {"name": "alpha", "package_version": "1"},
            ]},
            layout_content=[],
        )

        analysis = self._analyze()
        statuses = [item["status"] for item in analysis.dependencies]

        self.assertEqual(statuses.count("resolved_in_scan_root"), 2)
        self.assertEqual(statuses.count("outside_scan_scope"), 1)
        self.assertEqual(statuses.count("invalid"), 1)
        self.assertEqual(analysis.dependency_cycles, [["alpha", "beta"]])
