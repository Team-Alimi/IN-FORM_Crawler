"""Red tests for the v11 durable-state local runtime boundary."""

from __future__ import annotations

import importlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
import main as crawler_main
from common import logger
from dataprepper import deduplicate


class RuntimePathAndRedactionTests(unittest.TestCase):
    """Keep ephemeral runtime artifacts local, configurable, and secret-free."""

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.runtime_root = Path(self.temporary_directory.name)
        self.addCleanup(self.temporary_directory.cleanup)

    def tearDown(self):
        self._reset_logger()
        for name in (
            "CRAWLER_HISTORY_DIR",
            "CRAWLER_QUEUE_DIR",
            "CRAWLER_LOG_DIR",
        ):
            os.environ.pop(name, None)
        importlib.reload(config)

    @staticmethod
    def _reset_logger():
        if logger._logger is not None:
            for handler in list(logger._logger.handlers):
                logger._logger.removeHandler(handler)
                handler.close()
        logger._logger = None

    def test_runtime_paths_are_supplied_by_the_deployment_environment(self):
        paths = {
            "CRAWLER_HISTORY_DIR": self.runtime_root / "history",
            "CRAWLER_QUEUE_DIR": self.runtime_root / "queue",
            "CRAWLER_LOG_DIR": self.runtime_root / "logs",
        }

        with mock.patch.dict(
            os.environ,
            {name: str(path) for name, path in paths.items()},
            clear=False,
        ):
            reloaded_config = importlib.reload(config)

        self.assertEqual(reloaded_config.HISTORY_DIR, str(paths["CRAWLER_HISTORY_DIR"]))
        self.assertEqual(reloaded_config.QUEUE_DIR, str(paths["CRAWLER_QUEUE_DIR"]))
        self.assertEqual(reloaded_config.LOG_DIR, str(paths["CRAWLER_LOG_DIR"]))
        self.assertTrue(all(path.is_dir() for path in paths.values()))

    def test_runtime_paths_default_locally_without_state_transport_settings(self):
        for name in (
            "CRAWLER_HISTORY_DIR",
            "CRAWLER_QUEUE_DIR",
            "CRAWLER_LOG_DIR",
        ):
            os.environ.pop(name, None)
        reloaded_config = importlib.reload(config)
        config_source = Path(config.__file__).read_text(encoding="utf-8")

        self.assertEqual(
            reloaded_config.HISTORY_DIR,
            os.path.join(reloaded_config.DATA_ROOT, "history"),
        )
        self.assertEqual(
            reloaded_config.QUEUE_DIR,
            os.path.join(reloaded_config.DATA_ROOT, "queue"),
        )
        self.assertEqual(
            reloaded_config.LOG_DIR, os.path.join(reloaded_config.BASE_DIR, "log")
        )
        self.assertNotIn("CRAWLER_STATE_BUCKET", config_source)
        self.assertNotIn("CRAWLER_STATE_PREFIX", config_source)

    def test_clean_process_initializes_injected_paths_without_circular_import(self):
        paths = {
            "CRAWLER_HISTORY_DIR": self.runtime_root / "clean-history",
            "CRAWLER_QUEUE_DIR": self.runtime_root / "clean-queue",
            "CRAWLER_LOG_DIR": self.runtime_root / "clean-logs",
        }
        environment = os.environ | {name: str(path) for name, path in paths.items()}
        repository_root = Path(__file__).resolve().parents[2]

        result = subprocess.run(
            [sys.executable, "-c", "import main; print('runtime-config-ok')"],
            cwd=repository_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("runtime-config-ok", result.stdout)
        self.assertTrue(all(path.is_dir() for path in paths.values()))

    def test_queue_json_omits_sensitive_fields(self):
        queue_dir = self.runtime_root / "queue"
        secret = "test-only-queue-secret"
        payload = [
            {"title": "notice", "password": secret, "nested": {"api_key": secret}}
        ]

        with mock.patch.object(crawler_main, "QUEUE_DIR", str(queue_dir)):
            crawler_main.save_json(payload, "INSERT_DATA_redaction.json")

        serialized = (queue_dir / "INSERT_DATA_redaction.json").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(secret, serialized)
        self.assertNotIn('"password"', serialized)
        self.assertNotIn('"api_key"', serialized)

    def test_history_json_omits_sensitive_fields(self):
        history_dir = self.runtime_root / "history"
        secret = "test-only-history-secret"

        with mock.patch.object(deduplicate, "HISTORY_DIR", str(history_dir)):
            manager = deduplicate.HistoryManager("runtime-redaction")
            manager.update(
                {
                    "unique_id": "runtime-redaction-1",
                    "title": "notice",
                    "password": secret,
                    "nested": {"token": secret},
                }
            )
            manager.save()

        serialized = (history_dir / "runtime-redaction.json").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(secret, serialized)
        self.assertNotIn('"password"', serialized)
        self.assertNotIn('"token"', serialized)

    def test_file_and_stdout_logs_redact_sensitive_values(self):
        log_dir = self.runtime_root / "logs"
        secret = "test-only-log-secret"
        stdout = io.StringIO()

        self._reset_logger()
        with (
            mock.patch.object(logger, "LOG_DIR", str(log_dir)),
            mock.patch("sys.stdout", stdout),
        ):
            logger.init_logger("runtime-redaction")
            logger.log_status("Runtime", f"database password={secret}", "ERROR")

        log_files = list((log_dir / "runtime-redaction").glob("*.log"))
        self.assertEqual(len(log_files), 1)
        self.assertNotIn(secret, log_files[0].read_text(encoding="utf-8"))
        self.assertNotIn(secret, stdout.getvalue())
        self.assertIn("[Runtime]", stdout.getvalue())

    def test_status_log_writes_one_console_record(self):
        log_dir = self.runtime_root / "logs"
        stdout = io.StringIO()
        stderr = io.StringIO()

        self._reset_logger()
        with (
            mock.patch.object(logger, "LOG_DIR", str(log_dir)),
            mock.patch("sys.stdout", stdout),
            mock.patch("sys.stderr", stderr),
        ):
            logger.init_logger("runtime-single-console")
            logger.log_status("Runtime", "single console record", "SUCCESS")

        self.assertEqual(stdout.getvalue().count("[Runtime]"), 1)
        self.assertNotIn("[Runtime]", stderr.getvalue())

    def test_stdout_logging_tolerates_a_non_unicode_console(self):
        log_dir = self.runtime_root / "logs"
        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="ascii", errors="strict")

        self._reset_logger()
        with (
            mock.patch.object(logger, "LOG_DIR", str(log_dir)),
            mock.patch("sys.stdout", stdout),
        ):
            logger.init_logger("runtime-ascii")
            logger.log_status("Runtime", "console fallback check", "SUCCESS")
            stdout.flush()

        self.assertIn(b"[Runtime]", output.getvalue())


if __name__ == "__main__":
    unittest.main()
