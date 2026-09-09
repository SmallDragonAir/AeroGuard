import tempfile
import unittest
from pathlib import Path

from history import HistoryError, HistoryStore, build_snapshot, compare_snapshots


def make_report(*, packages, issues=None, resources=None, airports=None,
                dependencies=None, cycles=None, mode="quick"):
    issue_groups = {}
    for issue in issues or []:
        issue_groups.setdefault(issue["package"], []).append(issue)
    return {
        "schema_version": 1,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "community_path": "C:/Community",
        "scan_mode": mode,
        "summary": {},
        "timing": {"total_s": 1.25},
        "addons": [
            {
                "folder_name": name,
                "name": name.title(),
                "type": "SCENERY",
                "creator": "fixture",
                "version": version,
                "path": f"C:/Community/{name}",
            }
            for name, version in packages
        ],
        "issues_by_package": issue_groups,
        "scan_errors": [],
        "relationships": {
            "resource_conflicts": resources or [],
            "airport_conflicts": airports or [],
            "dependencies": dependencies or [],
            "dependency_cycles": cycles or [],
        },
    }


class HistoryTest(unittest.TestCase):

    def test_snapshot_is_compact_and_groups_issue_evidence(self):
        issue = {
            "package": "alpha",
            "rule_id": "LAYOUT_FILE_MISSING",
            "severity": "error",
            "affected_count": 2,
            "impact": "potentially_runtime",
            "details": ["a", "b"],
            "preview": ["a"],
        }
        report = make_report(packages=[("alpha", "1.0")], issues=[issue])

        snapshot = build_snapshot(report, snapshot_id="fixed", label="clean")

        self.assertEqual(snapshot["snapshot_id"], "fixed")
        self.assertEqual(snapshot["summary"]["issues"], 1)
        self.assertEqual(snapshot["issues"][0]["affected_count"], 2)
        self.assertIn("evidence_digest", snapshot["issues"][0])
        self.assertNotIn("details", snapshot["issues"][0])

    def test_compare_reports_package_issue_and_conflict_changes(self):
        baseline_report = make_report(
            packages=[("alpha", "1.0"), ("removed", "1.0")],
            issues=[{
                "package": "alpha", "rule_id": "RULE",
                "severity": "warning", "affected_count": 1,
                "details": ["old"],
            }],
            resources=[{
                "normalized_path": "effects/shared.fx",
                "severity": "info", "scope": "runtime_vfs",
                "packages": [{"package": "alpha"}, {"package": "removed"}],
                "intentional_overrides": [],
            }],
        )
        current_report = make_report(
            packages=[("alpha", "2.0"), ("added", "1.0")],
            issues=[{
                "package": "alpha", "rule_id": "RULE",
                "severity": "error", "affected_count": 2,
                "details": ["new"],
            }],
        )

        comparison = compare_snapshots(
            build_snapshot(baseline_report, snapshot_id="before"),
            build_snapshot(current_report, snapshot_id="after"),
        )

        self.assertEqual(len(comparison["packages"]["added"]), 1)
        self.assertEqual(len(comparison["packages"]["removed"]), 1)
        self.assertEqual(len(comparison["packages"]["changed"]), 1)
        self.assertEqual(len(comparison["issues"]["changed"]), 1)
        self.assertEqual(len(comparison["resource_conflicts"]["removed"]), 1)
        self.assertEqual(comparison["summary"]["total_changes"], 5)

    def test_scan_mode_mismatch_is_explicit(self):
        quick = build_snapshot(
            make_report(packages=[], mode="quick"), snapshot_id="quick"
        )
        full = build_snapshot(
            make_report(packages=[], mode="full"), snapshot_id="full"
        )

        comparison = compare_snapshots(quick, full)

        self.assertEqual(comparison["summary"]["compatibility_warnings"], 1)
        self.assertEqual(comparison["compatibility_warnings"][0]["field"],
                         "scan_mode")

    def test_store_records_lists_sets_and_compares_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            community = root / "Community"
            community.mkdir()
            store = HistoryStore(community, root / "state")
            first = store.record(
                make_report(packages=[("alpha", "1.0")]), label="initial"
            )
            baseline = store.set_baseline("stable", first["snapshot_id"])
            comparison = store.compare(
                "stable", make_report(packages=[("alpha", "2.0")])
            )

            self.assertEqual(len(store.list_snapshots()), 1)
            self.assertEqual(baseline["baseline_name"], "stable")
            self.assertEqual(len(comparison["packages"]["changed"]), 1)
            self.assertEqual(comparison["baseline_name"], "stable")

    def test_baseline_requires_explicit_replace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            community = root / "Community"
            community.mkdir()
            store = HistoryStore(community, root / "state")
            snapshot = store.record(make_report(packages=[]))
            store.set_baseline("stable", snapshot["snapshot_id"])

            with self.assertRaisesRegex(HistoryError, "--replace"):
                store.set_baseline("stable", snapshot["snapshot_id"])

            replaced = store.set_baseline(
                "stable", snapshot["snapshot_id"], replace=True
            )
            self.assertEqual(replaced["baseline_name"], "stable")


if __name__ == "__main__":
    unittest.main()
