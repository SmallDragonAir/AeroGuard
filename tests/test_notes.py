"""本地已知结论（notes）存储的单元测试。"""

import tempfile
import unittest
from pathlib import Path

from notes import MAX_NOTE_TEXT_LENGTH, NoteStore, NoteStoreError


class NoteStoreTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.community = root / "community"
        self.community.mkdir()
        (self.community / "pkg-a").mkdir()
        self.state = root / "state"
        self.addCleanup(self._tmp.cleanup)

    def _store(self):
        return NoteStore(self.community, self.state)

    def test_add_list_match(self):
        store = self._store()
        note = store.add("Pkg-A", "该差异由自更新器导致，可忽略",
                         rule_id="LAYOUT_FILE_SIZE_MISMATCH")

        listing = store.list("pkg-a")  # 大小写不敏感
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["notes"][0]["id"], note["id"])
        self.assertEqual(listing["notes"][0]["package"], "Pkg-A")
        self.assertEqual(listing["notes"][0]["source"], "manual")

    def test_list_all_and_package_filter(self):
        store = self._store()
        store.add("alpha", "备注 A")
        store.add("beta", "备注 B")

        self.assertEqual(store.list()["count"], 2)
        self.assertEqual(store.list("beta")["count"], 1)

    def test_remove(self):
        store = self._store()
        note = store.add("alpha", "待删除")

        removed = store.remove(note["id"])
        self.assertEqual(removed["id"], note["id"])
        self.assertEqual(store.list()["count"], 0)

        with self.assertRaises(NoteStoreError):
            store.remove(note["id"])

    def test_invalid_inputs_rejected(self):
        store = self._store()
        with self.assertRaises(NoteStoreError):
            store.add("", "x")
        with self.assertRaises(NoteStoreError):
            store.add("../escape", "x")
        with self.assertRaises(NoteStoreError):
            store.add("a/b", "x")
        with self.assertRaises(NoteStoreError):
            store.add("alpha", "   ")
        with self.assertRaises(NoteStoreError):
            store.add("alpha", "x" * (MAX_NOTE_TEXT_LENGTH + 1))

    def test_community_required_and_state_outside(self):
        missing = Path(self._tmp.name) / "no-such-community"
        with self.assertRaises(NoteStoreError):
            NoteStore(missing, self.state)

        with self.assertRaises(NoteStoreError):
            NoteStore(self.community, self.community / "inside")

    def test_corrupt_file_surfaces_error(self):
        store = self._store()
        store.add("alpha", "x")
        store.notes_path.write_text("{broken", encoding="utf-8")

        with self.assertRaises(NoteStoreError):
            store.list()

    def test_persists_between_instances(self):
        self._store().add("alpha", "持久化", rule_id="LAYOUT_FILE_MISSING")

        listing = self._store().list()
        self.assertEqual(listing["count"], 1)
        self.assertEqual(
            listing["notes"][0]["rule_id"], "LAYOUT_FILE_MISSING"
        )


if __name__ == "__main__":
    unittest.main()
