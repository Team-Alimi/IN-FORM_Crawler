"""Offline contract checks for the crawler-owned v11 queue payload."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from common.db_loader import prepare_v11_queue_payload

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "v11"
    / "crawler_writer_payload.json"
)

REQUIRED_SOURCE_IDENTITY = {"vendor_initial", "external_key", "source_url"}
FORBIDDEN_WRITER_KEYS = {
    "vendor_ids",
    "vendor_urls",
    "category_id",
    "status",
    "summary",
    "similar_article_id",
}


class V11WriterIdentityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with FIXTURE_PATH.open(encoding="utf-8") as fixture_file:
            cls.fixture = json.load(fixture_file)

    def test_queue_payload_uses_source_identity_not_legacy_numeric_ids(self):
        record = self.fixture["new_record"]

        self.assertEqual(self.fixture["contract_version"], "v11")
        self.assertEqual(record["source_type"], "SCHOOL")
        self.assertTrue(REQUIRED_SOURCE_IDENTITY.issubset(record))
        self.assertTrue(all(record[key] for key in REQUIRED_SOURCE_IDENTITY))
        self.assertFalse(FORBIDDEN_WRITER_KEYS.intersection(record))

    def test_payload_uses_canonical_category_and_external_attachments_only(self):
        record = self.fixture["new_record"]

        self.assertEqual(record["category_code"], "ETC")
        self.assertTrue(record["attachments"])
        for attachment in record["attachments"]:
            self.assertEqual(set(attachment), {"file_url"})
            self.assertTrue(attachment["file_url"])

    def test_similarity_payload_carries_candidate_identity_not_database_id(self):
        similarity = self.fixture["similarity"]

        self.assertGreaterEqual(similarity["score"], 0)
        self.assertLessEqual(similarity["score"], 100)
        self.assertTrue(
            REQUIRED_SOURCE_IDENTITY.difference({"source_url"}).issubset(similarity)
        )
        self.assertNotIn("similar_article_id", similarity)

    def test_queue_builder_removes_legacy_ids_and_normalizes_attachment_urls(self):
        raw_record = dict(self.fixture["new_record"])
        raw_record["vendor_ids"] = [101]
        raw_record["vendor_urls"] = [raw_record["source_url"]]
        raw_record["attachments"] = [
            {"attachment_url": "https://example.invalid/files/1001.pdf"}
        ]

        payload = prepare_v11_queue_payload(raw_record)

        self.assertFalse(FORBIDDEN_WRITER_KEYS.intersection(payload))
        self.assertEqual(
            payload["attachments"],
            [{"file_url": "https://example.invalid/files/1001.pdf"}],
        )


if __name__ == "__main__":
    unittest.main()
