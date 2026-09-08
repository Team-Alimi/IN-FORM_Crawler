"""Approved-target checks for the backend-owned V1–V14 Flyway contract.

The suite never applies DDL.  It runs only when both non-production DSNs are injected by the
backend-owned validation workflow; otherwise normal offline test runs skip it.
"""

import os
import unittest
import uuid

import psycopg

ADMIN_DSN_ENV = "INFORM_TEST_POSTGRES_DSN"
CRAWLER_DSN_ENV = "INFORM_TEST_CRAWLER_DSN"

EXPECTED_ACTIVE_CATEGORY_CODES = {
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


class V11FlywayDatabaseContractTests(unittest.TestCase):
    """Verify the applied backend artifact through admin and crawler-role connections."""

    @classmethod
    def setUpClass(cls):
        cls.admin_dsn = os.getenv(ADMIN_DSN_ENV)
        cls.crawler_dsn = os.getenv(CRAWLER_DSN_ENV)
        if not cls.admin_dsn or not cls.crawler_dsn:
            raise unittest.SkipTest(
                "approved non-production PostgreSQL DSNs are not configured"
            )

    def admin_connection(self):
        return psycopg.connect(self.admin_dsn, autocommit=True)

    def crawler_connection(self):
        return psycopg.connect(self.crawler_dsn, autocommit=True)

    def create_article(self, status):
        with self.admin_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO articles (source_type, title, content, status, published_at)
                VALUES ('SCHOOL', %s, %s, %s,
                        CASE WHEN %s = 'PUBLISHED' THEN now() ELSE NULL END)
                RETURNING id
                """,
                (
                    f"crawler contract test {status}",
                    "approved non-production contract fixture",
                    status,
                    status,
                ),
            )
            return cursor.fetchone()[0]

    def delete_article(self, article_id):
        with self.admin_connection() as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM articles WHERE id = %s", (article_id,))

    def create_school_vendor(self):
        initial = f"TST{uuid.uuid4().hex[:12]}"
        with self.admin_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO vendors (name, initial, type, homepage_url)
                VALUES (%s, %s, 'SCHOOL', %s)
                RETURNING id
                """,
                (
                    "crawler contract test vendor",
                    initial,
                    "https://example.invalid/crawler-contract-test",
                ),
            )
            return cursor.fetchone()[0]

    def delete_vendor(self, vendor_id):
        with self.admin_connection() as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM vendors WHERE id = %s", (vendor_id,))

    def test_flyway_history_is_exactly_v1_through_v14(self):
        with self.admin_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT version
                  FROM flyway_schema_history
                 WHERE success = true
                   AND version IS NOT NULL
                 ORDER BY installed_rank
                """
            )
            applied_versions = [row[0] for row in cursor.fetchall()]

        self.assertEqual(applied_versions, [str(number) for number in range(1, 15)])

    def test_status_is_required_without_a_database_default(self):
        with self.admin_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT is_nullable, column_default
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name = 'articles'
                   AND column_name = 'status'
                """
            )
            row = cursor.fetchone()

        self.assertEqual(row, ("NO", None))

    def test_crawler_session_and_effective_column_grants_match_v14(self):
        with self.crawler_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT session_user")
            self.assertEqual(cursor.fetchone()[0], "inform_crawler")
            cursor.execute(
                """
                SELECT
                    has_column_privilege(
                        'inform_crawler', 'public.articles', 'version', 'UPDATE'
                    ),
                    has_column_privilege(
                        'inform_crawler', 'public.articles', 'similarity_score', 'UPDATE'
                    ),
                    has_column_privilege(
                        'inform_crawler', 'public.articles', 'similar_article_id', 'UPDATE'
                    ),
                    has_column_privilege(
                        'inform_crawler', 'public.articles', 'status', 'UPDATE'
                    ),
                    has_column_privilege(
                        'inform_crawler', 'public.articles', 'summary', 'UPDATE'
                    )
                """
            )
            grants = cursor.fetchone()

        self.assertEqual(grants, (True, True, True, False, False))

    def test_v14_active_categories_and_crawler_only_etc_are_applied(self):
        with self.admin_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT code, is_selectable
                  FROM categories
                 WHERE is_active = true
                """
            )
            categories = dict(cursor.fetchall())

        self.assertEqual(set(categories), EXPECTED_ACTIVE_CATEGORY_CODES)
        self.assertFalse(categories["ETC"])
        self.assertTrue(all(categories[code] for code in categories if code != "ETC"))

    def test_crawler_material_update_preserves_trashed_and_audits_re_review(self):
        published_article_id = self.create_article("PUBLISHED")
        trashed_article_id = self.create_article("TRASHED")
        try:
            with self.crawler_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE articles
                       SET title = %s,
                           version = version + 1
                     WHERE id = %s
                    """,
                    ("crawler changed published article", published_article_id),
                )
                cursor.execute(
                    """
                    UPDATE articles
                       SET title = %s,
                           version = version + 1
                     WHERE id = %s
                    """,
                    ("crawler changed trashed article", trashed_article_id),
                )

            with self.admin_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT status FROM articles WHERE id = %s",
                    (published_article_id,),
                )
                self.assertEqual(cursor.fetchone()[0], "PENDING_REVIEW")
                cursor.execute(
                    """
                    SELECT from_status, to_status
                      FROM article_status_logs
                     WHERE article_id = %s
                     ORDER BY id DESC
                     LIMIT 1
                    """,
                    (published_article_id,),
                )
                self.assertEqual(cursor.fetchone(), ("PUBLISHED", "PENDING_REVIEW"))
                cursor.execute(
                    "SELECT status FROM articles WHERE id = %s",
                    (trashed_article_id,),
                )
                self.assertEqual(cursor.fetchone()[0], "TRASHED")
        finally:
            self.delete_article(published_article_id)
            self.delete_article(trashed_article_id)

    def test_crawler_source_rows_require_external_key_and_source_url(self):
        article_id = self.create_article("PENDING_REVIEW")
        vendor_id = self.create_school_vendor()
        try:
            with self.crawler_connection() as connection, connection.cursor() as cursor:
                with self.assertRaises(psycopg.Error) as raised:
                    cursor.execute(
                        """
                        INSERT INTO article_vendors (article_id, vendor_id)
                        VALUES (%s, %s)
                        """,
                        (article_id, vendor_id),
                    )

            self.assertEqual(raised.exception.sqlstate, "IN003")
        finally:
            self.delete_article(article_id)
            self.delete_vendor(vendor_id)


if __name__ == "__main__":
    unittest.main()
