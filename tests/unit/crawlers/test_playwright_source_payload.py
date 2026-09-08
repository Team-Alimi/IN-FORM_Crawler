import json
import unittest
from pathlib import Path

from crawlers.playwright.type_b import TypeBCrawler
from crawlers.playwright.type_c import TypeCCrawler
from crawlers.playwright.type_e import TypeECrawler

SITE = {
    "name": "Synthetic chemistry source",
    "vendor_initial": "CHM",
    "source_type": "SCHOOL",
    "url": "https://source.example.test/notices",
}


class PlaywrightSourcePayloadTests(unittest.TestCase):
    def test_types_b_c_and_e_use_vendor_initial_as_the_source_identity_prefix(self):
        for crawler_type in (TypeBCrawler, TypeCCrawler, TypeECrawler):
            with self.subTest(crawler_type=crawler_type.__name__):
                crawler = crawler_type(SITE)

                self.assertEqual(crawler.vendor_initial, "CHM")
                self.assertEqual(crawler.source_type, "SCHOOL")
                self.assertEqual(crawler.build_external_key("178913"), "CHM178913")
                self.assertFalse(hasattr(crawler, "vendor_id"))

    def test_types_b_c_and_e_reject_a_missing_native_identifier(self):
        for crawler_type in (TypeBCrawler, TypeCCrawler, TypeECrawler):
            with self.subTest(crawler_type=crawler_type.__name__):
                crawler = crawler_type(SITE)

                for missing_identifier in (None, "", "   "):
                    with self.subTest(missing_identifier=missing_identifier):
                        with self.assertRaises(ValueError):
                            crawler.build_external_key(missing_identifier)

    def test_type_b_c_and_e_seeds_use_only_v10_source_metadata(self):
        seed_directory = Path(__file__).resolve().parents[3] / "data" / "seeds"

        for seed_name in ("type_b.json", "type_c.json", "type_e.json"):
            with self.subTest(seed_name=seed_name):
                with (seed_directory / seed_name).open(
                    encoding="utf-8-sig"
                ) as seed_file:
                    seeds = json.load(seed_file)

                self.assertTrue(seeds)
                for seed in seeds:
                    self.assertEqual(seed["source_type"], "SCHOOL")
                    self.assertTrue(seed["vendor_initial"])
                    self.assertNotIn("vendor_id", seed)
                    self.assertNotIn("code", seed)


if __name__ == "__main__":
    unittest.main()
