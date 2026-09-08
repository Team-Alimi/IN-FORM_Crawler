"""Queue-backed PostgreSQL writer for the approved v11 crawler boundary."""

from __future__ import annotations

import glob
import json
import os

import psycopg

from common.logger import log_status
from config import (
    QUEUE_DIR,
    DatabaseConnectionRetryableError,
    connect_with_one_secret_refresh,
)

POSTGRES_SECRET_ID_ENV = "POSTGRES_SECRET_ID"
SOURCE_TYPE = "SCHOOL"


def _required_string(record, field):
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_date(record, field):
    value = record.get(field)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date or timestamp string")
    return value


def _prepare_attachments(attachments):
    if attachments is None:
        return []
    if not isinstance(attachments, list):
        raise ValueError("attachments must be a list")

    prepared = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            raise ValueError("each attachment must be an object")
        if set(attachment) != {"file_url"}:
            raise ValueError("crawler attachments must be EXTERNAL file_url objects")
        file_url = attachment.get("file_url")
        if not isinstance(file_url, str) or not file_url.strip():
            raise ValueError("attachment file_url is required")
        prepared.append({"file_url": file_url.strip()})
    return prepared


def prepare_v11_queue_payload(record):
    """Normalize one in-memory crawler record into the versioned queue payload."""
    if not isinstance(record, dict):
        raise ValueError("crawler record must be an object")

    attachments = []
    for attachment in record.get("attachments") or []:
        if not isinstance(attachment, dict):
            raise ValueError("each attachment must be an object")
        file_url = attachment.get("file_url", attachment.get("attachment_url"))
        attachments.append({"file_url": file_url})

    payload = {
        "source_type": record.get("source_type"),
        "vendor_initial": record.get("vendor_initial"),
        "external_key": record.get("external_key"),
        "source_url": record.get("source_url"),
        "title": record.get("title"),
        "content": record.get("content"),
        "start_date": record.get("start_date"),
        "due_date": record.get("due_date"),
        "published_at": record.get("published_at"),
        "category_code": record.get("category_code"),
        "attachments": attachments,
    }
    if record.get("similarity") is not None:
        payload["similarity"] = record["similarity"]
    return payload


def _validate_record(record):
    if not isinstance(record, dict):
        raise ValueError("queue record must be an object")
    if record.get("source_type") != SOURCE_TYPE:
        raise ValueError("crawler writer accepts SCHOOL records only")

    return {
        "vendor_initial": _required_string(record, "vendor_initial"),
        "external_key": _required_string(record, "external_key"),
        "source_url": _required_string(record, "source_url"),
        "title": _required_string(record, "title"),
        "content": _required_string(record, "content"),
        "start_date": _optional_date(record, "start_date"),
        "due_date": _optional_date(record, "due_date"),
        "published_at": _optional_date(record, "published_at"),
        "category_code": _required_string(record, "category_code"),
        "attachments": _prepare_attachments(record.get("attachments")),
        "similarity": record.get("similarity"),
    }


def _lookup_vendor_id(cursor, vendor_initial):
    cursor.execute(
        """
        SELECT id FROM vendors
         WHERE initial = %s AND type = 'SCHOOL' AND is_active = true
        """,
        (vendor_initial,),
    )
    row = cursor.fetchone()
    if row is None:
        raise LookupError("SCHOOL vendor_initial could not be resolved")
    return row[0]


def _lookup_category_id(cursor, category_code):
    cursor.execute(
        """
        SELECT id FROM categories
         WHERE code = %s AND is_active = true
        """,
        (category_code,),
    )
    row = cursor.fetchone()
    if row is None:
        raise LookupError("active category_code could not be resolved")
    return row[0]


def _resolve_similarity(cursor, similarity):
    if similarity is None:
        return None, None
    if not isinstance(similarity, dict) or set(similarity) != {
        "score",
        "vendor_initial",
        "external_key",
    }:
        raise ValueError("similarity must contain score and candidate source identity")

    score = similarity["score"]
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValueError("similarity score must be numeric")
    if not 0 <= score <= 100:
        raise ValueError("similarity score must be between 0 and 100")

    vendor_initial = _required_string(similarity, "vendor_initial")
    external_key = _required_string(similarity, "external_key")
    cursor.execute(
        """
        SELECT a.id
          FROM articles AS a
          JOIN article_vendors AS av ON av.article_id = a.id
          JOIN vendors AS v ON v.id = av.vendor_id
         WHERE v.initial = %s AND av.external_key = %s
        """,
        (vendor_initial, external_key),
    )
    row = cursor.fetchone()
    if row is None:
        raise LookupError("similar candidate could not be resolved")
    return float(score), row[0]


def _sync_category_and_external_attachments(
    cursor, article_id, category_id, attachments
):
    cursor.execute(
        "DELETE FROM article_categories WHERE article_id = %s", (article_id,)
    )
    cursor.execute(
        "INSERT INTO article_categories (article_id, category_id) VALUES (%s, %s)",
        (article_id, category_id),
    )
    cursor.execute(
        "DELETE FROM attachments WHERE article_id = %s AND storage_type = 'EXTERNAL'",
        (article_id,),
    )
    for position, attachment in enumerate(attachments):
        cursor.execute(
            """
            INSERT INTO attachments (article_id, file_url, storage_type, object_key, sort_order)
            VALUES (%s, %s, 'EXTERNAL', NULL, %s)
            """,
            (article_id, attachment["file_url"], position),
        )


def _insert_record(
    cursor, record, vendor_id, category_id, similarity_score, similar_article_id
):
    cursor.execute(
        """
        INSERT INTO articles (
            source_type, title, content, starts_on, ends_on, published_at, status,
            similarity_score, similar_article_id
        )
        VALUES ('SCHOOL', %s, %s, %s, %s, %s, 'PENDING_REVIEW', %s, %s)
        RETURNING id
        """,
        (
            record["title"],
            record["content"],
            record["start_date"],
            record["due_date"],
            record["published_at"],
            similarity_score,
            similar_article_id,
        ),
    )
    article_id = cursor.fetchone()[0]
    cursor.execute(
        """
        INSERT INTO article_vendors (article_id, vendor_id, external_key, source_url)
        VALUES (%s, %s, %s, %s)
        """,
        (article_id, vendor_id, record["external_key"], record["source_url"]),
    )
    _sync_category_and_external_attachments(
        cursor, article_id, category_id, record["attachments"]
    )


def _find_source_article(cursor, vendor_id, external_key):
    cursor.execute(
        """
        SELECT a.id, a.version, a.title, a.content, a.starts_on, a.ends_on,
               a.similarity_score, a.similar_article_id
          FROM articles AS a
          JOIN article_vendors AS av ON av.article_id = a.id
         WHERE av.vendor_id = %s AND av.external_key = %s
        """,
        (vendor_id, external_key),
    )
    return cursor.fetchone()


def _date_matches(database_value, payload_value):
    if database_value is None:
        return payload_value is None
    return database_value.isoformat() == payload_value


def _update_record(
    cursor, record, vendor_id, category_id, similarity_score, similar_article_id
):
    row = _find_source_article(cursor, vendor_id, record["external_key"])
    if row is None:
        raise LookupError("source record could not be resolved for update")
    (
        article_id,
        version,
        existing_title,
        existing_content,
        existing_starts_on,
        existing_ends_on,
        existing_similarity_score,
        existing_similar_article_id,
    ) = row
    has_material_change = any(
        (
            existing_title != record["title"],
            existing_content != record["content"],
            not _date_matches(existing_starts_on, record["start_date"]),
            not _date_matches(existing_ends_on, record["due_date"]),
            existing_similarity_score != similarity_score,
            existing_similar_article_id != similar_article_id,
        )
    )
    if has_material_change:
        cursor.execute(
            """
            UPDATE articles
               SET title = %s,
                   content = %s,
                   starts_on = %s,
                   ends_on = %s,
                   version = version + 1,
                   similarity_score = %s,
                   similar_article_id = %s
             WHERE id = %s AND version = %s
            """,
            (
                record["title"],
                record["content"],
                record["start_date"],
                record["due_date"],
                similarity_score,
                similar_article_id,
                article_id,
                version,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("article version conflict")
    cursor.execute(
        """
        UPDATE article_vendors
           SET source_url = %s
         WHERE article_id = %s AND vendor_id = %s AND external_key = %s
        """,
        (record["source_url"], article_id, vendor_id, record["external_key"]),
    )
    _sync_category_and_external_attachments(
        cursor, article_id, category_id, record["attachments"]
    )


def _execute_load(cursor, data, mode):
    if not isinstance(data, list):
        raise ValueError("queue JSON root must be a list")
    if mode not in {"INSERT", "UPDATE"}:
        raise ValueError("unsupported queue mode")

    for raw_record in data:
        record = _validate_record(raw_record)
        vendor_id = _lookup_vendor_id(cursor, record["vendor_initial"])
        category_id = _lookup_category_id(cursor, record["category_code"])
        similarity_score, similar_article_id = _resolve_similarity(
            cursor, record["similarity"]
        )
        if mode == "INSERT":
            if _find_source_article(cursor, vendor_id, record["external_key"]):
                _update_record(
                    cursor,
                    record,
                    vendor_id,
                    category_id,
                    similarity_score,
                    similar_article_id,
                )
            else:
                _insert_record(
                    cursor,
                    record,
                    vendor_id,
                    category_id,
                    similarity_score,
                    similar_article_id,
                )
        else:
            _update_record(
                cursor,
                record,
                vendor_id,
                category_id,
                similarity_score,
                similar_article_id,
            )


def _connect_from_credentials(credentials):
    try:
        return psycopg.connect(
            host=credentials["host"],
            port=credentials["port"],
            dbname=credentials["dbname"],
            user=credentials["username"],
            password=credentials["password"],
        )
    except psycopg.OperationalError as error:
        raise DatabaseConnectionRetryableError(
            "PostgreSQL connection failed"
        ) from error


def _runtime_connection():
    return connect_with_one_secret_refresh(
        os.getenv(POSTGRES_SECRET_ID_ENV), None, _connect_from_credentials
    )


def load_json_to_db(connection_factory=None):
    """Load queued v11 records and remove queue input only after a successful commit."""
    connection_factory = connection_factory or _runtime_connection
    connection = None
    committed = False
    loaded_paths = []

    try:
        connection = connection_factory()
        with connection.cursor() as cursor:
            queue_files = [
                (path, "INSERT")
                for path in sorted(
                    glob.glob(os.path.join(QUEUE_DIR, "INSERT_DATA*.json"))
                )
            ]
            queue_files.extend(
                (path, "UPDATE")
                for path in sorted(
                    glob.glob(os.path.join(QUEUE_DIR, "UPDATE_DATA*.json"))
                )
            )
            for path, mode in queue_files:
                with open(path, "r", encoding="utf-8") as queue_file:
                    data = json.load(queue_file)
                _execute_load(cursor, data, mode)
                loaded_paths.append(path)
                log_status(
                    "DBLoader",
                    f"{os.path.basename(path)}: {len(data)} {mode.title()} loaded",
                    "SUCCESS",
                )

        connection.commit()
        committed = True
        for path in loaded_paths:
            os.remove(path)
    except Exception as error:
        if connection is not None and not committed:
            try:
                connection.rollback()
            except Exception:
                pass
        log_status("DBLoader", f"database load failed: {type(error).__name__}", "ERROR")
        raise
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    load_json_to_db()
