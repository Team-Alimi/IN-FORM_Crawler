"""Offline checks for the adopted v11/V14 crawler master-data boundary."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from config import (
    CANONICAL_CATEGORY_CODES,
    category_code_allows_write,
    normalize_category_code,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
V11_SNAPSHOT_PATH = (
    REPOSITORY_ROOT
    / ".agents"
    / "docs"
    / "contracts"
    / "v11-school-vendor-master-data-snapshot.json"
)
V10_VENDOR_SNAPSHOT_PATH = (
    REPOSITORY_ROOT
    / ".agents"
    / "docs"
    / "contracts"
    / "v10-school-vendor-master-data-snapshot.json"
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


class V11MasterDataContractTests(unittest.TestCase):
    def test_v14_category_snapshot_has_twelve_active_codes_and_crawler_only_etc(self):
        with V11_SNAPSHOT_PATH.open(encoding="utf-8") as snapshot_file:
            snapshot = json.load(snapshot_file)

        categories = {entry["code"]: entry for entry in snapshot["categories"]}

        self.assertEqual(snapshot["contract"], "v11-school-vendor-master-data-snapshot")
        self.assertEqual(set(categories), EXPECTED_CRAWLER_CODES)
        self.assertTrue(all(entry["is_active"] for entry in categories.values()))
        self.assertFalse(categories["ETC"]["is_selectable"])
        self.assertTrue(
            all(
                entry["is_selectable"]
                for code, entry in categories.items()
                if code != "ETC"
            )
        )

    def test_current_category_boundary_matches_v14_and_keeps_etc_distinct_from_missing(
        self,
    ):
        self.assertEqual(set(CANONICAL_CATEGORY_CODES), EXPECTED_CRAWLER_CODES)
        self.assertEqual(normalize_category_code(" etc "), "ETC")
        self.assertTrue(category_code_allows_write("ETC"))

        for invalid in ("EXCLUDE", "SEMINAR", "UNKNOWN", 0, None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    normalize_category_code(invalid)

    def test_v11_contract_preserves_the_approved_school_vendor_inventory_by_reference(
        self,
    ):
        with V11_SNAPSHOT_PATH.open(encoding="utf-8") as snapshot_file:
            v11_snapshot = json.load(snapshot_file)
        with V10_VENDOR_SNAPSHOT_PATH.open(encoding="utf-8") as snapshot_file:
            vendor_snapshot = json.load(snapshot_file)

        reference = v11_snapshot["vendor_inventory_reference"]
        self.assertEqual(
            reference["contract"], "v10-school-vendor-master-data-snapshot.json@1.0.0"
        )
        self.assertEqual(
            reference["unique_vendor_count"], vendor_snapshot["unique_vendor_count"]
        )
        self.assertEqual(
            reference["seed_source_digest_sha256"],
            vendor_snapshot["seed_source_digest_sha256"],
        )
        self.assertTrue(
            all(
                vendor["source_type"] == "SCHOOL"
                for vendor in vendor_snapshot["vendors"]
            )
        )


if __name__ == "__main__":
    unittest.main()
