import json
import os
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from scrapy.exceptions import DropItem
from scrapy.http import HtmlResponse

from crawlers.scrapy_app.items import InformArticle
from crawlers.scrapy_app.pipelines import ValidationPipeline
from crawlers.scrapy_app.spiders.type_a import TypeASpider
from crawlers.scrapy_app.spiders.type_d import TypeDSpider

SITE = {
    "name": "Synthetic chemistry source",
    "vendor_initial": "CHM",
    "source_type": "SCHOOL",
    "url": "https://source.example.test/notices",
}


class ScrapySourcePayloadTests(unittest.TestCase):
    def _spider(self, spider_type):
        with patch.dict(
            os.environ, {"SCRAPY_SITE_INFO": json.dumps(SITE)}, clear=False
        ):
            return spider_type()

    def test_type_a_emits_v10_source_identity_instead_of_numeric_vendor_identity(self):
        spider = self._spider(TypeASpider)
        response = HtmlResponse(
            url="https://source.example.test/notices/178913",
            body=b'<div class="artclView"><p>body</p></div>',
            encoding="utf-8",
        )

        item = dict(next(spider.parse_detail(response, "A title", "178913")))

        self.assertEqual(item["vendor_initial"], "CHM")
        self.assertEqual(item["source_type"], "SCHOOL")
        self.assertEqual(item["external_key"], "CHM178913")
        self.assertEqual(item["source_url"], response.url)
        self.assertNotIn("vendor_id", item)
        self.assertNotIn("vendor_ids", item)

    def test_type_d_emits_v10_source_identity_instead_of_timestamp_fallback(self):
        spider = self._spider(TypeDSpider)
        response = HtmlResponse(
            url="https://source.example.test/notices/178913",
            body=b'<div class="board-view-cnt"><p>body</p></div>',
            encoding="utf-8",
        )

        item = dict(
            next(
                spider.parse_detail(
                    response,
                    "D title",
                    "178913",
                    datetime(2026, 1, 15, 9, 0, 0),
                )
            )
        )

        self.assertEqual(item["vendor_initial"], "CHM")
        self.assertEqual(item["source_type"], "SCHOOL")
        self.assertEqual(item["external_key"], "CHM178913")
        self.assertEqual(item["source_url"], response.url)
        self.assertNotIn("vendor_id", item)
        self.assertNotIn("vendor_ids", item)

    def test_type_a_and_d_seeds_use_only_v10_source_metadata(self):
        seed_directory = Path(__file__).resolve().parents[3] / "data" / "seeds"

        for seed_name in ("type_a.json", "type_d.json"):
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

        semiconductor = next(
            seed
            for seed in json.loads(
                (seed_directory / "type_a.json").read_text(encoding="utf-8-sig")
            )
            if seed["name"] == "반도체시스템공학과"
        )
        self.assertEqual(semiconductor["vendor_initial"], "SES")

    def test_validation_pipeline_preserves_v10_identity_and_rejects_missing_fields(
        self,
    ):
        article = InformArticle(
            unique_id="CHM178913",
            title="A title",
            content="body",
            original_url="https://source.example.test/notices/178913",
            vendor_initial="CHM",
            source_type="SCHOOL",
            external_key="CHM178913",
            source_url="https://source.example.test/notices/178913",
        )

        with patch(
            "crawlers.scrapy_app.pipelines.process_article",
            side_effect=lambda value: value,
        ):
            cleaned = ValidationPipeline().process_item(article, spider=None)

        self.assertEqual(cleaned["external_key"], "CHM178913")
        self.assertEqual(cleaned["vendor_initial"], "CHM")

        incomplete = InformArticle(
            unique_id="CHM178913",
            title="A title",
            content="body",
            original_url="https://source.example.test/notices/178913",
            source_type="SCHOOL",
            external_key="CHM178913",
            source_url="https://source.example.test/notices/178913",
        )

        with self.assertRaises(DropItem):
            ValidationPipeline().process_item(incomplete, spider=None)


if __name__ == "__main__":
    unittest.main()
