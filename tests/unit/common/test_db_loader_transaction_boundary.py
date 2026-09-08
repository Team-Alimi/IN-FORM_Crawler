"""Transaction-boundary tests for the v11 queue-backed PostgreSQL loader."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from common import db_loader


class FakeCursor:
    def __init__(self, execute_error=None):
        self.execute_error = execute_error

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class FakeConnection:
    def __init__(self, cursor=None, commit_error=None, events=None):
        self._cursor = cursor or FakeCursor()
        self.commit_error = commit_error
        self.events = events if events is not None else []
        self.rollback_called = False
        self.close_called = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.events.append("commit")
        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        self.rollback_called = True
        self.events.append("rollback")

    def close(self):
        self.close_called = True


class DatabaseLoaderTransactionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.queue_dir = Path(self.temporary_directory.name)
        self.queue_dir_patch = mock.patch.object(
            db_loader, "QUEUE_DIR", str(self.queue_dir)
        )
        self.queue_dir_patch.start()
        self.addCleanup(self.queue_dir_patch.stop)
        self.addCleanup(self.temporary_directory.cleanup)

    def write_queue(self, name, payload):
        path = self.queue_dir / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    @staticmethod
    def article_payload():
        return [{"source_type": "SCHOOL", "title": "notice"}]

    def test_connection_error_is_logged_and_propagated(self):
        connection_factory = mock.Mock(side_effect=OSError("connect failed"))

        with (
            mock.patch.object(db_loader, "log_status") as log_status,
            self.assertRaisesRegex(OSError, "connect failed"),
        ):
            db_loader.load_json_to_db(connection_factory=connection_factory)

        log_status.assert_called()

    def test_malformed_queue_is_retained_and_error_propagates_after_rollback(self):
        path = self.queue_dir / "INSERT_DATA_malformed.json"
        path.write_text("{not-json", encoding="utf-8")
        connection = FakeConnection()

        with (
            mock.patch.object(db_loader, "log_status"),
            self.assertRaises(json.JSONDecodeError),
        ):
            db_loader.load_json_to_db(connection_factory=lambda: connection)

        self.assertTrue(path.exists())
        self.assertTrue(connection.rollback_called)
        self.assertTrue(connection.close_called)

    def test_sql_error_rolls_back_retains_queue_and_propagates(self):
        path = self.write_queue("INSERT_DATA_sql.json", self.article_payload())
        connection = FakeConnection()

        with (
            mock.patch.object(
                db_loader, "_execute_load", side_effect=RuntimeError("sql failed")
            ),
            mock.patch.object(db_loader, "log_status"),
            self.assertRaisesRegex(RuntimeError, "sql failed"),
        ):
            db_loader.load_json_to_db(connection_factory=lambda: connection)

        self.assertTrue(path.exists())
        self.assertTrue(connection.rollback_called)
        self.assertTrue(connection.close_called)

    def test_commit_error_rolls_back_retains_queue_and_propagates(self):
        path = self.write_queue("INSERT_DATA_commit.json", self.article_payload())
        connection = FakeConnection(commit_error=RuntimeError("commit failed"))

        with (
            mock.patch.object(db_loader, "_execute_load"),
            mock.patch.object(db_loader, "log_status"),
            self.assertRaisesRegex(RuntimeError, "commit failed"),
        ):
            db_loader.load_json_to_db(connection_factory=lambda: connection)

        self.assertTrue(path.exists())
        self.assertTrue(connection.rollback_called)
        self.assertTrue(connection.close_called)

    def test_success_commits_before_queue_cleanup(self):
        path = self.write_queue("INSERT_DATA_success.json", self.article_payload())
        events = []
        connection = FakeConnection(events=events)
        real_remove = os.remove

        def record_cleanup(queue_path):
            events.append("cleanup")
            real_remove(queue_path)

        with (
            mock.patch.object(db_loader, "_execute_load"),
            mock.patch.object(db_loader, "log_status"),
            mock.patch.object(db_loader.os, "remove", side_effect=record_cleanup),
        ):
            db_loader.load_json_to_db(connection_factory=lambda: connection)

        self.assertEqual(["commit", "cleanup"], events)
        self.assertFalse(path.exists())
        self.assertTrue(connection.close_called)


if __name__ == "__main__":
    unittest.main()
