import copy
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from dataprepper.unifier import Unifier

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "v10"
    / "source_unification_cases.json"
)


class AlwaysSimilarEngine:
    def fuzzy_match(self, _title, _other_title):
        return True

    def get_jaccard_similarity(self, _article, _other_article):
        return 1.0


class GreyZoneEngine:
    def fuzzy_match(self, _title, _other_title):
        return False

    def get_jaccard_similarity(self, _article, _other_article):
        return 0.40


class SourcePreservingUnificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with FIXTURE_PATH.open(encoding="utf-8") as fixture_file:
            cls.cases = {
                case["name"]: case for case in json.load(fixture_file)["cases"]
            }

    def _unify(self, records, engine_class=AlwaysSimilarEngine):
        similarity_module = types.ModuleType("dataprepper.similarity_engine")
        similarity_module.SimilarityEngine = engine_class
        similarity_module.JACCARD_THRESHOLD = 0.48

        with tempfile.TemporaryDirectory() as history_directory:
            with (
                patch("dataprepper.unifier.HISTORY_DIR", history_directory),
                patch("dataprepper.deduplicate.HISTORY_DIR", history_directory),
                patch.dict(
                    sys.modules, {"dataprepper.similarity_engine": similarity_module}
                ),
            ):
                return Unifier().unify(records)

    def test_same_source_retry_collapses_by_vendor_and_external_key(self):
        inserts, updates = self._unify(
            copy.deepcopy(
                self.cases["same_source_retry_uses_one_stable_identity"]["records"]
            )
        )

        self.assertEqual(updates, [])
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0]["external_key"], "CHM178913")
        self.assertEqual(
            inserts[0]["source_url"],
            "https://source.example.test/board/view?article=178913",
        )

    def test_similar_notices_from_distinct_sources_remain_separate_candidates(self):
        inserts, updates = self._unify(
            copy.deepcopy(
                self.cases["different_sources_are_not_collapsed_by_content_similarity"][
                    "records"
                ]
            )
        )

        self.assertEqual(updates, [])
        self.assertEqual(len(inserts), 2)
        self.assertEqual(
            {article["external_key"] for article in inserts}, {"CHM178913", "SES1001"}
        )
        self.assertEqual(
            {article["vendor_initial"] for article in inserts}, {"CHM", "SES"}
        )

    def test_unification_does_not_add_preprocessing_fields_to_source_records(self):
        records = copy.deepcopy(
            self.cases["same_source_retry_uses_one_stable_identity"]["records"]
        )
        original_records = copy.deepcopy(records)

        self._unify(records)

        self.assertEqual(records, original_records)

    def test_jaccard_grey_zone_does_not_emit_legacy_duplicate_status(self):
        inserts, updates = self._unify(
            copy.deepcopy(
                self.cases["same_source_retry_uses_one_stable_identity"]["records"]
            ),
            GreyZoneEngine,
        )

        self.assertEqual(updates, [])
        self.assertTrue(inserts)
        self.assertTrue(all("admin_status" not in article for article in inserts))


if __name__ == "__main__":
    unittest.main()
