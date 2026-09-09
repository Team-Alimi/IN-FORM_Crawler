"""Red integration checks for the v11 PostgreSQL crawler writer boundary."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest import mock

import psycopg

import dataprepper
import dataprepper.ai_engine
import main as crawler_main
from common import db_loader

ADMIN_DSN_ENV = "INFORM_TEST_POSTGRES_DSN"
CRAWLER_DSN_ENV = "INFORM_TEST_CRAWLER_DSN"
FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "v11"
    / "crawler_writer_payload.json"
)


class V11CrawlerWriterIntegrationTests(unittest.TestCase):
    """Exercise the unchanged loader entry point against the approved non-production target."""

    @classmethod
    def setUpClass(cls):
        cls.admin_dsn = os.getenv(ADMIN_DSN_ENV)
        cls.crawler_dsn = os.getenv(CRAWLER_DSN_ENV)
        if not cls.admin_dsn or not cls.crawler_dsn:
            raise unittest.SkipTest(
                "approved non-production PostgreSQL DSNs are not configured"
            )
        with FIXTURE_PATH.open(encoding="utf-8") as fixture_file:
            cls.fixture = json.load(fixture_file)

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.queue_dir = Path(self.temporary_directory.name)
        self.queue_patch = mock.patch.object(
            db_loader, "QUEUE_DIR", str(self.queue_dir)
        )
        self.queue_patch.start()
        self.addCleanup(self.queue_patch.stop)
        self.addCleanup(self.temporary_directory.cleanup)
        self.created_articles = []
        self.created_vendors = []

    def tearDown(self):
        with self.admin_connection() as connection, connection.cursor() as cursor:
            for article_id in self.created_articles:
                cursor.execute("DELETE FROM articles WHERE id = %s", (article_id,))
            for vendor_id in self.created_vendors:
                cursor.execute("DELETE FROM vendors WHERE id = %s", (vendor_id,))

    def admin_connection(self):
        return psycopg.connect(self.admin_dsn, autocommit=True)

    def crawler_connection(self):
        return psycopg.connect(self.crawler_dsn)

    def create_vendor(self):
        initial = f"TST{uuid.uuid4().hex[:12]}"
        with self.admin_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO vendors (name, initial, type, homepage_url)
                VALUES (%s, %s, 'SCHOOL', %s)
                RETURNING id
                """,
                (
                    "v11 crawler writer test vendor",
                    initial,
                    "https://example.invalid/v11-writer-test",
                ),
            )
            vendor_id = cursor.fetchone()[0]
        self.created_vendors.append(vendor_id)
        return vendor_id, initial

    def create_source_article(self, vendor_id, external_key, status="PENDING_REVIEW"):
        with self.admin_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO articles (source_type, title, content, status, published_at)
                VALUES ('SCHOOL', %s, %s, %s,
                        CASE WHEN %s = 'PUBLISHED' THEN now() ELSE NULL END)
                RETURNING id, version
                """,
                ("existing source", "existing content", status, status),
            )
            article_id, version = cursor.fetchone()
            cursor.execute(
                """
                INSERT INTO article_vendors (article_id, vendor_id, external_key, source_url)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    article_id,
                    vendor_id,
                    external_key,
                    f"https://example.invalid/notices/{external_key}",
                ),
            )
        self.created_articles.append(article_id)
        return article_id, version

    def write_queue(self, mode, record):
        path = self.queue_dir / f"{mode}_DATA_v11.json"
        path.write_text(json.dumps([record]), encoding="utf-8")
        return path

    def payload(self, vendor_initial, external_key):
        record = copy.deepcopy(self.fixture["new_record"])
        record["vendor_initial"] = vendor_initial
        record["external_key"] = external_key
        record["source_url"] = f"https://example.invalid/notices/{external_key}"
        return record

    def run_loader(self):
        return db_loader.load_json_to_db(connection_factory=self.crawler_connection)

    def find_article(self, vendor_id, external_key):
        with self.admin_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT a.id, a.status, a.version, a.similarity_score,
                       a.similar_article_id, c.code, att.storage_type,
                       att.object_key, att.file_url
                  FROM articles AS a
                  JOIN article_vendors AS av ON av.article_id = a.id
             LEFT JOIN article_categories AS ac ON ac.article_id = a.id
             LEFT JOIN categories AS c ON c.id = ac.category_id
             LEFT JOIN attachments AS att ON att.article_id = a.id
                 WHERE av.vendor_id = %s AND av.external_key = %s
                """,
                (vendor_id, external_key),
            )
            return cursor.fetchone()

    def test_new_record_commits_all_four_domains_before_queue_cleanup(self):
        vendor_id, vendor_initial = self.create_vendor()
        external_key = "new-record"
        queue_path = self.write_queue(
            "INSERT", self.payload(vendor_initial, external_key)
        )

        self.run_loader()

        row = self.find_article(vendor_id, external_key)
        self.assertIsNotNone(row)
        self.created_articles.append(row[0])
        self.assertEqual(row[1], "PENDING_REVIEW")
        self.assertEqual(row[5], "ETC")
        self.assertEqual(row[6], "EXTERNAL")
        self.assertIsNone(row[7])
        self.assertEqual(row[8], "https://example.invalid/files/1001.pdf")
        self.assertFalse(queue_path.exists())

    def test_retry_after_post_commit_queue_cleanup_error_is_idempotent(self):
        vendor_id, vendor_initial = self.create_vendor()
        external_key = "cleanup-retry-record"
        queue_path = self.write_queue(
            "INSERT", self.payload(vendor_initial, external_key)
        )

        with (
            mock.patch.object(
                db_loader.os, "remove", side_effect=OSError("cleanup failed")
            ),
            self.assertRaisesRegex(OSError, "cleanup failed"),
        ):
            self.run_loader()

        first_row = self.find_article(vendor_id, external_key)
        self.assertIsNotNone(first_row)
        self.created_articles.append(first_row[0])
        self.assertTrue(queue_path.exists())

        self.run_loader()

        second_row = self.find_article(vendor_id, external_key)
        self.assertEqual(second_row[0], first_row[0])
        self.assertEqual(second_row[1], first_row[1])
        self.assertEqual(second_row[2], first_row[2])
        self.assertFalse(queue_path.exists())

    def test_similarity_candidate_is_resolved_from_source_identity(self):
        vendor_id, vendor_initial = self.create_vendor()
        candidate_id, _ = self.create_source_article(vendor_id, "candidate")
        external_key = "similar-record"
        record = self.payload(vendor_initial, external_key)
        record["similarity"] = {
            "score": 85.0,
            "vendor_initial": vendor_initial,
            "external_key": "candidate",
        }
        self.write_queue("INSERT", record)

        self.run_loader()

        row = self.find_article(vendor_id, external_key)
        self.assertIsNotNone(row)
        self.created_articles.append(row[0])
        self.assertEqual(float(row[3]), 85.0)
        self.assertEqual(row[4], candidate_id)

    def test_unresolved_similarity_candidate_rolls_back_and_retains_queue(self):
        vendor_id, vendor_initial = self.create_vendor()
        external_key = "unresolved-record"
        record = self.payload(vendor_initial, external_key)
        record["similarity"] = {
            "score": 85.0,
            "vendor_initial": vendor_initial,
            "external_key": "missing-candidate",
        }
        queue_path = self.write_queue("INSERT", record)

        with self.assertRaisesRegex(Exception, r"(?i)similar.*candidate"):
            self.run_loader()

        self.assertIsNone(self.find_article(vendor_id, external_key))
        self.assertTrue(queue_path.exists())

    def test_update_increments_version_and_preserves_trashed_status(self):
        vendor_id, vendor_initial = self.create_vendor()
        external_key = "trashed-record"
        article_id, original_version = self.create_source_article(
            vendor_id, external_key, status="TRASHED"
        )
        record = self.payload(vendor_initial, external_key)
        record["title"] = "materially updated title"
        record["content"] = "materially updated content"
        queue_path = self.write_queue("UPDATE", record)

        self.run_loader()

        with self.admin_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT status, version, title FROM articles WHERE id = %s",
                (article_id,),
            )
            status, version, title = cursor.fetchone()
        self.assertEqual(status, "TRASHED")
        self.assertEqual(version, original_version + 1)
        self.assertEqual(title, "materially updated title")
        self.assertFalse(queue_path.exists())

    def test_non_external_attachment_is_rejected_without_a_partial_write(self):
        vendor_id, vendor_initial = self.create_vendor()
        external_key = "s3-attachment-record"
        record = self.payload(vendor_initial, external_key)
        record["attachments"] = [
            {
                "file_url": "https://example.invalid/files/forbidden.pdf",
                "storage_type": "S3",
                "object_key": "forbidden-object",
            }
        ]
        queue_path = self.write_queue("INSERT", record)

        with self.assertRaisesRegex(Exception, r"(?i)external"):
            self.run_loader()

        self.assertIsNone(self.find_article(vendor_id, external_key))
        self.assertTrue(queue_path.exists())


class V11MainPersistenceOrderTests(unittest.TestCase):
    """Keep history advancement behind the v11 queue and writer success boundary."""

    @staticmethod
    def article():
        return {
            "source_type": "SCHOOL",
            "vendor_initial": "TST_VENDOR",
            "external_key": "main-order-record",
            "source_url": "https://example.invalid/notices/main-order-record",
            "title": "notice",
            "content": "body",
            "category_code": "ETC",
            "attachments": [],
        }

    def run_main(self, loader, events):
        unifier = mock.Mock()
        unifier.unify.return_value = ([self.article()], [])
        unifier.commit.side_effect = lambda *_: events.append("history")
        unifier_module = types.ModuleType("dataprepper.unifier")
        unifier_module.Unifier = mock.Mock(return_value=unifier)
        ai = mock.Mock()
        ai.process.side_effect = lambda records: records
        ai_module = types.ModuleType("dataprepper.ai_engine.base")
        ai_module.AI = mock.Mock(return_value=ai)

        with (
            mock.patch.object(sys, "argv", ["main.py", "--type", "A"]),
            mock.patch.object(crawler_main, "init_logger"),
            mock.patch.object(crawler_main, "log_status"),
            mock.patch.object(
                crawler_main, "load_sites", return_value=[{"type": "A", "name": "site"}]
            ),
            mock.patch.object(
                crawler_main,
                "run_crawler",
                new=mock.AsyncMock(return_value=("site", [self.article()])),
            ),
            mock.patch.object(dataprepper, "unifier", unifier_module, create=True),
            mock.patch.object(dataprepper.ai_engine, "base", ai_module, create=True),
            mock.patch.dict(
                sys.modules,
                {
                    "dataprepper.unifier": unifier_module,
                    "dataprepper.ai_engine.base": ai_module,
                },
            ),
            mock.patch.object(
                crawler_main,
                "save_json",
                side_effect=lambda *_: events.append("queue"),
            ),
            mock.patch("common.db_loader.load_json_to_db", side_effect=loader),
        ):
            asyncio.run(crawler_main.main())

        return unifier

    def test_history_advances_only_after_v11_queue_and_writer_success(self):
        events = []
        unifier = self.run_main(lambda: events.append("writer"), events)

        self.assertEqual(events, ["queue", "queue", "writer", "history"])
        unifier.commit.assert_called_once()

    def test_writer_failure_does_not_advance_history_for_a_v11_payload(self):
        events = []

        with self.assertRaisesRegex(RuntimeError, "writer failed"):
            self.run_main(mock.Mock(side_effect=RuntimeError("writer failed")), events)

        self.assertEqual(events, ["queue", "queue"])


if __name__ == "__main__":
    unittest.main()
