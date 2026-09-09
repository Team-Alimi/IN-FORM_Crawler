"""Red integration tests for orchestration failure visibility and persistence ordering."""

import asyncio
import sys
import types
import unittest
from unittest import mock

import common
import dataprepper
import dataprepper.ai_engine
import main as crawler_main


class MainPersistenceOrderTests(unittest.TestCase):
    @staticmethod
    def article():
        return {
            "source_type": "SCHOOL",
            "vendor_initial": "TST_VENDOR",
            "external_key": "source-1",
            "source_url": "https://example.invalid/notices/source-1",
            "title": "notice",
            "content": "body",
            "attachments": [],
            "category_code": "ETC",
        }

    def run_main(
        self,
        run_crawler,
        *,
        ai_process=None,
        loader=None,
        history_commit=None,
        events=None,
    ):
        events = events if events is not None else []
        unifier = mock.Mock()
        unifier.unify.return_value = ([self.article()], [])
        unifier.commit.side_effect = history_commit or (
            lambda inserts, updates: events.append("history")
        )
        ai = mock.Mock()
        ai.process.side_effect = ai_process or (lambda records: records)
        unifier_module = types.ModuleType("dataprepper.unifier")
        unifier_module.Unifier = mock.Mock(return_value=unifier)
        ai_module = types.ModuleType("dataprepper.ai_engine.base")
        ai_module.AI = mock.Mock(return_value=ai)
        db_loader_module = types.ModuleType("common.db_loader")
        db_loader_module.prepare_v11_queue_payload = lambda article: article
        db_loader_module.load_json_to_db = mock.Mock(
            side_effect=loader or (lambda: events.append("loader"))
        )
        self.last_unifier = unifier
        self.last_events = events

        with (
            mock.patch.object(sys, "argv", ["main.py", "--type", "A"]),
            mock.patch.object(crawler_main, "init_logger"),
            mock.patch.object(crawler_main, "log_status"),
            mock.patch.object(
                crawler_main, "load_sites", return_value=[{"type": "A", "name": "site"}]
            ),
            mock.patch.object(crawler_main, "run_crawler", new=run_crawler),
            mock.patch.object(dataprepper, "unifier", unifier_module, create=True),
            mock.patch.object(dataprepper.ai_engine, "base", ai_module, create=True),
            mock.patch.object(common, "db_loader", db_loader_module, create=True),
            mock.patch.dict(
                sys.modules,
                {
                    "dataprepper.unifier": unifier_module,
                    "dataprepper.ai_engine.base": ai_module,
                    "common.db_loader": db_loader_module,
                },
            ),
            mock.patch.object(
                crawler_main,
                "save_json",
                side_effect=lambda *args: events.append("queue"),
            ),
        ):
            asyncio.run(crawler_main.main())

        return unifier, events

    def test_successful_run_records_history_only_after_queue_and_loader_success(self):
        unifier, events = self.run_main(
            mock.AsyncMock(return_value=("site", [self.article()]))
        )

        self.assertEqual(["queue", "queue", "loader", "history"], events)
        unifier.commit.assert_called_once()

    def test_loader_failure_does_not_advance_history(self):
        with self.assertRaisesRegex(RuntimeError, "load failed"):
            self.run_main(
                mock.AsyncMock(return_value=("site", [self.article()])),
                loader=mock.Mock(side_effect=RuntimeError("load failed")),
            )

        self.assertFalse(self.last_unifier.commit.called)
        self.assertEqual(["queue", "queue"], self.last_events)

    def test_collector_exception_is_a_non_successful_run(self):
        with self.assertRaises(RuntimeError):
            self.run_main(mock.AsyncMock(side_effect=RuntimeError("collector failed")))

    def test_ai_exception_stops_before_loader_or_history(self):
        with self.assertRaisesRegex(RuntimeError, "ai failed"):
            self.run_main(
                mock.AsyncMock(return_value=("site", [self.article()])),
                ai_process=mock.Mock(side_effect=RuntimeError("ai failed")),
            )

        self.assertFalse(self.last_unifier.commit.called)
        self.assertEqual([], self.last_events)

    def test_history_failure_remains_non_successful_after_loader(self):
        def fail_history(inserts, updates):
            events.append("history")
            raise OSError("history failed")

        events = []
        with self.assertRaisesRegex(OSError, "history failed"):
            self.run_main(
                mock.AsyncMock(return_value=("site", [self.article()])),
                history_commit=fail_history,
                events=events,
            )

        self.assertEqual(["queue", "queue", "loader", "history"], events)


if __name__ == "__main__":
    unittest.main()
