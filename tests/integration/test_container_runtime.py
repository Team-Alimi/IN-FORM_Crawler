"""Red tests for controlled ephemeral-worker interruption behavior."""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

import main as crawler_main


class ContainerInterruptionTests(unittest.TestCase):
    @staticmethod
    def article():
        return {
            "source_type": "SCHOOL",
            "vendor_initial": "TST_VENDOR",
            "external_key": "interruption-source",
            "source_url": "https://example.invalid/notices/interruption-source",
            "title": "notice",
            "content": "body",
            "category_code": "ETC",
            "attachments": [],
        }

    def test_interruption_after_queue_prevents_loader_and_history_success(self):
        events = []
        interruption_event = asyncio.Event()
        unifier = mock.Mock()
        unifier.unify.return_value = ([self.article()], [])
        unifier_module = types.ModuleType("dataprepper.unifier")
        unifier_module.Unifier = mock.Mock(return_value=unifier)
        ai = mock.Mock()
        ai.process.side_effect = lambda records: records
        ai_module = types.ModuleType("dataprepper.ai_engine.base")
        ai_module.AI = mock.Mock(return_value=ai)
        db_loader_module = types.ModuleType("common.db_loader")
        db_loader_module.prepare_v11_queue_payload = lambda article: article
        db_loader_module.load_json_to_db = mock.Mock()

        def save_queue(*_):
            events.append("queue")
            if events == ["queue", "queue"]:
                interruption_event.set()

        with (
            mock.patch.object(crawler_main.sys, "argv", ["main.py", "--type", "A"]),
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
            mock.patch.dict(
                sys.modules,
                {
                    "dataprepper.unifier": unifier_module,
                    "dataprepper.ai_engine.base": ai_module,
                    "common.db_loader": db_loader_module,
                },
            ),
            mock.patch.object(crawler_main, "save_json", side_effect=save_queue),
            self.assertRaisesRegex(crawler_main.RuntimeInterruption, "interrupted"),
        ):
            asyncio.run(crawler_main.main(interruption_event=interruption_event))

        self.assertEqual(events, ["queue", "queue"])
        db_loader_module.load_json_to_db.assert_not_called()
        unifier.commit.assert_not_called()

    def test_docker_entrypoint_delivers_termination_signals_to_python(self):
        dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
        dockerfile_text = dockerfile.read_text(encoding="utf-8")

        self.assertIn('ENTRYPOINT ["python", "main.py"]', dockerfile_text)


if __name__ == "__main__":
    unittest.main()
