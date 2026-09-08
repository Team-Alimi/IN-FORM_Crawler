"""Red tests for atomic, non-mutating local history persistence."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dataprepper.deduplicate import HistoryManager
from dataprepper.unifier import Unifier


class HistoryPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.history_dir = Path(self.tmp_dir.name)
        self.history_patch = mock.patch(
            "dataprepper.deduplicate.HISTORY_DIR", str(self.history_dir)
        )
        self.meta_patch = mock.patch(
            "dataprepper.unifier.HISTORY_DIR", str(self.history_dir)
        )
        self.history_patch.start()
        self.meta_patch.start()
        self.addCleanup(self.history_patch.stop)
        self.addCleanup(self.meta_patch.stop)
        self.addCleanup(self.tmp_dir.cleanup)

    @staticmethod
    def article():
        return {
            "unique_id": "SRC1",
            "site_name": "source",
            "vendor_initial": "SRC",
            "source_type": "SCHOOL",
            "external_key": "SRC1",
            "source_url": "https://example.test/notice/1",
            "title": "notice",
            "content": "body",
            "attachments": [],
        }

    def test_missing_history_is_empty_but_malformed_history_is_not_silently_ignored(
        self,
    ):
        self.assertEqual({}, HistoryManager("missing").data)

        (self.history_dir / "broken.json").write_text("{not-json", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            HistoryManager("broken")

    def test_malformed_meta_is_not_silently_ignored(self):
        (self.history_dir / "GLOBAL_CONTENT_HASH.json").write_text(
            "{not-json", encoding="utf-8"
        )

        with self.assertRaises(json.JSONDecodeError):
            Unifier()

    def test_invalid_history_shape_is_not_silently_ignored(self):
        (self.history_dir / "invalid-shape.json").write_text(
            json.dumps(["not an article"]), encoding="utf-8"
        )

        with self.assertRaises(ValueError):
            HistoryManager("invalid-shape")

    def test_invalid_meta_shape_is_not_silently_ignored(self):
        (self.history_dir / "GLOBAL_CONTENT_HASH.json").write_text(
            json.dumps({"fingerprint": "not metadata"}), encoding="utf-8"
        )

        with self.assertRaises(ValueError):
            Unifier()

    def test_commit_does_not_mutate_caller_article(self):
        article = self.article()
        before = copy.deepcopy(article)

        Unifier().commit([article], [])

        self.assertEqual(before, article)

    def test_history_replace_failure_preserves_existing_file(self):
        path = self.history_dir / "source.json"
        original = [{"unique_id": "existing", "title": "old", "content": "old"}]
        path.write_text(json.dumps(original), encoding="utf-8")
        manager = HistoryManager("source")
        manager.update(self.article())

        with (
            mock.patch(
                "dataprepper.deduplicate.os.replace",
                side_effect=OSError("replace failed"),
            ),
            self.assertRaisesRegex(OSError, "replace failed"),
        ):
            manager.save()

        self.assertEqual(original, json.loads(path.read_text(encoding="utf-8")))

    def test_meta_replace_failure_preserves_existing_file(self):
        path = self.history_dir / "GLOBAL_CONTENT_HASH.json"
        original = {"existing": {"title": "old"}}
        path.write_text(json.dumps(original), encoding="utf-8")
        unifier = Unifier()
        unifier.meta = {"replacement": {"title": "new"}}

        with (
            mock.patch(
                "dataprepper.deduplicate.os.replace",
                side_effect=OSError("replace failed"),
            ),
            self.assertRaisesRegex(OSError, "replace failed"),
        ):
            unifier._save_meta()

        self.assertEqual(original, json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
