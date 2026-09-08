"""Offline V11/V14 payload-boundary checks for source identity and category semantics."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "v11"
    / "source_identity_cases.json"
)

EXPECTED_CRAWLER_CODES = {
    "ACADEMIC",
    "ACTIVITY",
    "CAREER",
    "CERTIFICATION",
    "CONTEST",
    "EVENT",
    "FOREIGN",
    "LECTURE",
    "RESEARCH",
    "SCHOLARSHIP",
    "VOLUNTEER",
    "ETC",
}


class V11PayloadContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with FIXTURE_PATH.open(encoding="utf-8") as fixture_file:
            cls.fixture = json.load(fixture_file)

    def test_fixture_uses_the_effective_v14_category_contract(self):
        self.assertEqual(
            set(self.fixture["canonical_categories"]), EXPECTED_CRAWLER_CODES
        )
        self.assertNotIn("EXCLUDE", self.fixture["canonical_categories"])

    def test_pre_filter_rejection_has_no_category_or_write_candidate(self):
        cases = {case["name"]: case for case in self.fixture["source_identity_cases"]}
        excluded = cases["pre_filter_excluded_before_ai_classification"]

        self.assertTrue(excluded["pre_filter_excluded"])
        self.assertFalse(excluded["article_write_candidate"])
        self.assertNotIn("category", excluded)

    def test_valid_uncategorized_notice_uses_etc_and_preserves_source_identity(self):
        cases = {case["name"]: case for case in self.fixture["source_identity_cases"]}
        etc_notice = cases["valid_uncategorized_notice_uses_etc"]

        self.assertEqual(etc_notice["category"], "ETC")
        self.assertTrue(etc_notice["article_write_candidate"])
        self.assertEqual(
            etc_notice["external_key"],
            etc_notice["vendor_initial"] + etc_notice["native_post_id"],
        )


if __name__ == "__main__":
    unittest.main()
