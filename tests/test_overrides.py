"""本地规则覆盖（overrides）存储的单元测试。"""

import tempfile
import unittest
from pathlib import Path

from overrides import OverrideStore, OverrideStoreError


class OverrideStoreTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.community = root / "community"
        self.community.mkdir()
        self.state = root / "state"
        self.addCleanup(self._tmp.cleanup)

    def _store(self):
        return OverrideStore(self.community, self.state)

    def test_add_list_match(self):
        store = self._store()
        record = store.add(
            "pkg-a", "layout_file_missing", "ignore",
            reason="known safe",
        )

        listing = store.list("PKG-A")
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["overrides"][0]["id"], record["id"])
        # rule_id 统一大写
        self.assertEqual(listing["overrides"][0]["rule_id"], "LAYOUT_FILE_MISSING")

    def test_list_filter_by_rule(self):
        store = self._store()
        store.add("alpha", "LAYOUT_FILE_MISSING", "ignore")
        store.add("alpha", "LAYOUT_UNLISTED_FILE", "downgrade")

        self.assertEqual(store.list()["count"], 2)
        self.assertEqual(
            store.list("alpha", "LAYOUT_UNLISTED_FILE")["count"], 1
        )

    def test_duplicate_package_rule_rejected(self):
        store = self._store()
        store.add("alpha", "X_RULE", "ignore")
        with self.assertRaises(OverrideStoreError):
            store.add("ALPHA", "x_rule", "downgrade")

    def test_remove(self):
        store = self._store()
        record = store.add("alpha", "R1", "ignore", reason="r")
        self.assertEqual(store.remove(record["id"])["id"], record["id"])
        self.assertEqual(store.list()["count"], 0)
        with self.assertRaises(OverrideStoreError):
            store.remove(record["id"])

    def test_invalid_inputs(self):
        store = self._store()
        with self.assertRaises(OverrideStoreError):
            store.add("", "R", "ignore")
        with self.assertRaises(OverrideStoreError):
            store.add("a/b", "R", "ignore")
        with self.assertRaises(OverrideStoreError):
            store.add("alpha", "", "ignore")
        with self.assertRaises(OverrideStoreError):
            store.add("alpha", "R", "delete")

    def test_persists(self):
        self._store().add("alpha", "R", "downgrade", reason="x")
        listing = self._store().list()
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["overrides"][0]["action"], "downgrade")

    def test_state_outside_community(self):
        with self.assertRaises(OverrideStoreError):
            OverrideStore(self.community, self.community / "inside")

    def test_corrupt_file(self):
        store = self._store()
        store.add("alpha", "R", "ignore")
        store.overrides_path.write_text("{bad", encoding="utf-8")
        with self.assertRaises(OverrideStoreError):
            store.list()


if __name__ == "__main__":
    unittest.main()
