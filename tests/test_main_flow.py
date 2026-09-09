"""验证 main.run_full_diagnosis 这一唯一诊断入口的契约。

CLI（main.main）、GUI（gui.run_desktop_scan）与历史记录
（history_cli._run_report）都应通过它执行扫描，防止逻辑分叉。
"""

import tempfile
import unittest
from pathlib import Path

from .fixtures import make_addon
from main import run_full_diagnosis, run_scan
from relationships import RelationshipAnalysis
from report import build_report


class FullDiagnosisContractTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.community = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _build_community(self):
        make_addon(
            self.community,
            "alpha",
            layout_content=[
                {"path": "SimObjects/A/panel.cfg", "size": 5},
                {"path": "html_ui/main.js", "size": 4},
            ],
            files={
                "SimObjects/A/panel.cfg": b"12345",
                "html_ui/main.js": b"1234",
            },
        )
        make_addon(
            self.community,
            "beta",
            layout_content=[
                {"path": "html_ui/main.js", "size": 99},
            ],
        )

    def test_run_full_diagnosis_shape(self):
        self._build_community()

        (addons, scan_errors, issues, stats,
         relationships, timing) = run_full_diagnosis(
            self.community, full_scan=True
        )

        self.assertEqual(len(addons), 2)
        self.assertIsInstance(relationships, RelationshipAnalysis)
        self.assertIn("relationships", timing)
        self.assertGreaterEqual(timing["relationships"], 0.0)
        # total 已包含关系分析时间
        self.assertGreaterEqual(
            timing["total"],
            timing.get("analyzer", 0.0) + timing["relationships"],
        )
        # 完整扫描应发现 beta 缺失文件与资源重叠
        rule_ids = {issue["rule_id"] for issue in issues}
        self.assertIn("LAYOUT_FILE_MISSING", rule_ids)

    def test_run_scan_excludes_relationships(self):
        self._build_community()

        _addons, _errors, _issues, _stats, timing = run_scan(
            self.community, full_scan=False
        )
        self.assertNotIn("relationships", timing)

    def test_skip_relationships_returns_none_and_no_timing(self):
        self._build_community()

        (addons, scan_errors, issues, stats,
         relationships, timing) = run_full_diagnosis(
            self.community, full_scan=False,
            with_relationships=False,
        )

        self.assertEqual(len(addons), 2)
        self.assertIsNone(relationships)
        self.assertNotIn("relationships", timing)
        # 跳过时 total 不再累加关系分析时间
        self.assertGreaterEqual(timing["total"], timing.get("analyzer", 0.0))

    def test_report_builds_with_full_diagnosis_output(self):
        self._build_community()

        (addons, scan_errors, issues, stats,
         relationships, timing) = run_full_diagnosis(
            self.community, full_scan=False
        )
        document = build_report(
            community_path=self.community,
            scan_mode="quick",
            addons=addons,
            scan_errors=scan_errors,
            issues=issues,
            stats=stats,
            timing=timing,
            relationships=relationships,
        )

        self.assertEqual(document["summary"]["addons"], 2)
        self.assertIsNotNone(document["relationships"])
        self.assertIn("relationships_s", document["timing"])
        # 两个包声明了同一 runtime VFS 路径 → 至少一条资源冲突候选
        self.assertGreaterEqual(
            document["relationships"]["summary"]["resource_conflicts"], 1
        )


if __name__ == "__main__":
    unittest.main()
