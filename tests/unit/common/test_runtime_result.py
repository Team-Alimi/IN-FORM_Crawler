import unittest

from common.runtime_result import (
    RuntimeConfigurationError,
    RuntimeExitCode,
    classify_runtime_error,
)
from config import (
    DatabaseConnectionRetryableError,
    DatabaseSecretConfigurationError,
)


class _SqlStateError(RuntimeError):
    def __init__(self, sqlstate):
        super().__init__("synthetic database error")
        self.sqlstate = sqlstate


class _AwsAuthorizationError(RuntimeError):
    response = {"Error": {"Code": "AccessDeniedException"}}


class RuntimeResultContractTests(unittest.TestCase):
    def test_uses_stable_sysexits_codes(self):
        self.assertEqual(0, RuntimeExitCode.SUCCESS)
        self.assertEqual(65, RuntimeExitCode.SCHEMA_CONTRACT_ERROR)
        self.assertEqual(70, RuntimeExitCode.DETERMINISTIC_APPLICATION_ERROR)
        self.assertEqual(75, RuntimeExitCode.DB_CONNECTION_TRANSIENT)
        self.assertEqual(77, RuntimeExitCode.AUTHORIZATION_ERROR)
        self.assertEqual(78, RuntimeExitCode.INVALID_CONFIGURATION)

    def test_classifies_retryable_database_connection_failure(self):
        error = DatabaseConnectionRetryableError("synthetic connection failure")

        self.assertEqual(
            RuntimeExitCode.DB_CONNECTION_TRANSIENT,
            classify_runtime_error(error),
        )

    def test_authorization_cause_overrides_retryable_wrapper(self):
        error = DatabaseConnectionRetryableError("synthetic connection failure")
        error.__cause__ = _SqlStateError("28P01")

        self.assertEqual(
            RuntimeExitCode.AUTHORIZATION_ERROR,
            classify_runtime_error(error),
        )

    def test_classifies_aws_authorization_failure(self):
        self.assertEqual(
            RuntimeExitCode.AUTHORIZATION_ERROR,
            classify_runtime_error(_AwsAuthorizationError()),
        )

    def test_classifies_secret_and_runtime_configuration_failures(self):
        for error in (
            DatabaseSecretConfigurationError("synthetic secret configuration"),
            RuntimeConfigurationError("synthetic runtime configuration"),
        ):
            with self.subTest(error=type(error).__name__):
                self.assertEqual(
                    RuntimeExitCode.INVALID_CONFIGURATION,
                    classify_runtime_error(error),
                )

    def test_classifies_known_schema_contract_failure(self):
        self.assertEqual(
            RuntimeExitCode.SCHEMA_CONTRACT_ERROR,
            classify_runtime_error(_SqlStateError("42P01")),
        )

    def test_unknown_failure_is_non_retryable(self):
        self.assertEqual(
            RuntimeExitCode.DETERMINISTIC_APPLICATION_ERROR,
            classify_runtime_error(RuntimeError("synthetic application failure")),
        )


if __name__ == "__main__":
    unittest.main()
