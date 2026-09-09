import unittest
from unittest import mock

import main as crawler_main
from common.runtime_result import RuntimeExitCode
from config import DatabaseConnectionRetryableError


class MainRuntimeResultBoundaryTests(unittest.TestCase):
    def test_run_process_returns_retryable_database_exit_code(self):
        with (
            mock.patch.object(
                crawler_main,
                "run_cli",
                new=mock.AsyncMock(
                    side_effect=DatabaseConnectionRetryableError("synthetic failure"),
                ),
            ),
            mock.patch.object(crawler_main, "log_status"),
        ):
            actual = crawler_main.run_process()

        self.assertEqual(RuntimeExitCode.DB_CONNECTION_TRANSIENT, actual)

    def test_run_process_fails_unknown_exception_safely(self):
        with (
            mock.patch.object(
                crawler_main,
                "run_cli",
                new=mock.AsyncMock(side_effect=RuntimeError("synthetic failure")),
            ),
            mock.patch.object(crawler_main, "log_status"),
        ):
            actual = crawler_main.run_process()

        self.assertEqual(RuntimeExitCode.DETERMINISTIC_APPLICATION_ERROR, actual)


if __name__ == "__main__":
    unittest.main()
