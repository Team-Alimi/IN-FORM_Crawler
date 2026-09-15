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
        unified=None,
    ):
        events = events if events is not None else []
        unifier = mock.Mock()
        unifier.unify.return_value = (
            unified if unified is not None else ([self.article()], [])
        )
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
        save_json = mock.Mock(side_effect=lambda *args: events.append("queue"))
        log_status = mock.Mock()
        self.last_unifier = unifier
        self.last_unifier_factory = unifier_module.Unifier
        self.last_ai = ai
        self.last_ai_factory = ai_module.AI
        self.last_loader = db_loader_module.load_json_to_db
        self.last_events = events
        self.last_save_json = save_json
        self.last_log_status = log_status

        with (
            mock.patch.object(sys, "argv", ["main.py", "--type", "A"]),
            mock.patch.object(crawler_main, "init_logger"),
            mock.patch.object(crawler_main, "log_status", new=log_status),
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
                new=save_json,
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

    def test_attachment_only_articles_are_excluded_from_queue_and_history(self):
        raw_valid = self.article()
        valid_insert = self.article()
        valid_update = {**self.article(), "external_key": "source-2"}
        invalid_whitespace = {
            **self.article(),
            "external_key": "source-3",
            "content": "   ",
            "attachments": [{"attachment_url": "https://example.invalid/image-1.png"}],
        }
        invalid_non_string = {
            **self.article(),
            "external_key": "source-4",
            "content": ["unexpected"],
            "attachments": [{"attachment_url": "https://example.invalid/image-2.png"}],
        }

        unifier, _ = self.run_main(
            mock.AsyncMock(
                return_value=(
                    "site",
                    [raw_valid, invalid_whitespace, invalid_non_string],
                )
            ),
            unified=([valid_insert], [valid_update]),
        )

        unifier.unify.assert_called_once_with([raw_valid])
        self.assertEqual(
            [
                mock.call([valid_insert], "INSERT_DATA.json"),
                mock.call([valid_update], "UPDATE_DATA.json"),
            ],
            self.last_save_json.call_args_list,
        )
        self.assertEqual(
            [mock.call([valid_insert]), mock.call([valid_update])],
            self.last_ai.process.call_args_list,
        )
        unifier.commit.assert_called_once_with([valid_insert], [valid_update])
        self.last_log_status.assert_any_call(
            "System",
            "v11 필수 본문 없음으로 제외: 2건",
            "WARN",
        )

    def test_all_attachment_only_articles_skip_ai_loader_and_history(self):
        invalid_insert = {
            **self.article(),
            "content": "",
            "attachments": [{"attachment_url": "https://example.invalid/image.png"}],
        }

        unifier, events = self.run_main(
            mock.AsyncMock(return_value=("site", [invalid_insert])),
        )

        self.assertEqual(["queue", "queue"], events)
        self.assertEqual(
            [
                mock.call([], "INSERT_DATA.json"),
                mock.call([], "UPDATE_DATA.json"),
            ],
            self.last_save_json.call_args_list,
        )
        self.last_unifier_factory.assert_not_called()
        self.last_ai_factory.assert_not_called()
        self.last_loader.assert_not_called()
        unifier.commit.assert_not_called()
        self.last_log_status.assert_any_call(
            "System",
            "v11 필수 본문 없음으로 제외: 1건",
            "WARN",
        )


if __name__ == "__main__":
    unittest.main()
