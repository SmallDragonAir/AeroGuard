"""knowledge.apply_known_context 的应用逻辑单元测试。"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from .fixtures import make_addon
from knowledge import apply_known_context
from main import run_diagnosis_with_context
from notes import NoteStore
from overrides import OverrideStore


def make_issue(package, rule_id, severity="warning", affected=1):
    return {
        "rule_id": rule_id,
        "severity": severity,
        "package": package,
        "message": rule_id,
        "affected_count": affected,
        "details": [rule_id],
        "preview": [rule_id],
    }


def fake_store(kind, entries):
    key = "notes" if kind == "notes" else "overrides"
    return SimpleNamespace(list=lambda: {key: entries})


NOTE = {"id": "n1", "package": "Alpha", "rule_id": "X_RULE", "text": "已知差异"}
OV = {
    "id": "o1", "package": "Alpha", "rule_id": "X_RULE",
    "action": "ignore", "reason": "safe",
}


class ApplyKnownContextTest(unittest.TestCase):

    def test_attaches_matching_notes(self):
        store = fake_store("notes", [NOTE])
        issues = apply_known_context(
            [make_issue("Alpha", "X_RULE")], [], note_store=store
        )
        self.assertEqual(issues[0]["notes"][0]["text"], "已知差异")

    def test_note_rule_scoped(self):
        store = fake_store("notes", [NOTE])  # rule_id=X_RULE
        issues = apply_known_context(
            [make_issue("Alpha", "OTHER_RULE")], [], note_store=store
        )
        self.assertNotIn("notes", issues[0])

    def test_package_case_insensitive(self):
        store = fake_store("notes", [
            {"id": "n", "package": "Alpha", "rule_id": None, "text": "x"},
        ])
        issues = apply_known_context(
            [make_issue("alpha", "R")], [], note_store=store
        )
        self.assertEqual(issues[0]["notes"][0]["text"], "x")

    def test_ignore_removes_issue(self):
        store = fake_store("overrides", [OV])
        result = apply_known_context(
            [make_issue("Alpha", "X_RULE"), make_issue("Beta", "X_RULE")],
            [], override_store=store,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["package"], "Beta")

    def test_downgrade_sets_info_and_override(self):
        store = fake_store("overrides", [
            {**OV, "id": "o2", "action": "downgrade", "reason": "noise"},
        ])
        result = apply_known_context(
            [make_issue("Alpha", "X_RULE", severity="error")],
            [], override_store=store,
        )
        self.assertEqual(result[0]["severity"], "info")
        self.assertEqual(result[0]["override"]["action"], "downgrade")
        self.assertEqual(result[0]["override"]["reason"], "noise")

    def test_no_stores_no_change(self):
        issue = make_issue("Alpha", "X_RULE", severity="error")
        result = apply_known_context([issue], [])
        self.assertEqual(result[0], issue)
        self.assertNotIn("notes", result[0])
        self.assertNotIn("override", result[0])


class KnowledgeIntegrationTest(unittest.TestCase):
    """端到端：真实 temp 状态目录中的 notes/overrides 影响扫描结果。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.community = root / "community"
        self.community.mkdir()
        self.state = root / "state"
        self.addCleanup(self._tmp.cleanup)

    def test_overrides_and_notes_apply_to_scan(self):
        # addon-a 声明了一个缺失文件（会被 overrides 忽略）
        make_addon(
            self.community, "addon-a",
            layout_content=[{"path": "gone.txt", "size": 1}],
        )
        # addon-b 有一个未登记文件（被 note 标记为已知）
        make_addon(
            self.community, "addon-b",
            layout_content=[],
            files={"extra.txt": b"x"},
        )

        OverrideStore(self.community, self.state).add(
            "addon-a", "LAYOUT_FILE_MISSING", "ignore", reason="known"
        )
        NoteStore(self.community, self.state).add(
            "addon-b", "该未登记文件为运行期生成",
            rule_id="LAYOUT_UNLISTED_FILE",
        )

        (addons, scan_errors, issues, stats,
         relationships, timing) = run_diagnosis_with_context(
            self.community, full_scan=True, state_dir=self.state
        )

        self.assertEqual(len(addons), 2)
        rule_ids = {issue["rule_id"] for issue in issues}
        # addon-a 的缺失文件被忽略
        self.assertNotIn("LAYOUT_FILE_MISSING", rule_ids)
        # addon-b 的未登记文件保留，并带有已知结论
        unlisted = next(
            issue for issue in issues
            if issue["rule_id"] == "LAYOUT_UNLISTED_FILE"
        )
        self.assertEqual(unlisted["package"], "addon-b")
        self.assertEqual(unlisted["notes"][0]["text"], "该未登记文件为运行期生成")


if __name__ == "__main__":
    unittest.main()
