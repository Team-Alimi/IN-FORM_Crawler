import json
import unittest
from unittest.mock import Mock

from config import (
    DatabaseConnectionRetryableError,
    DatabaseSecretConfigurationError,
    connect_with_one_secret_refresh,
    resolve_postgres_database_secret,
)


class PostgreSQLConnectionConfigContractTests(unittest.TestCase):
    secret_id = "arn:aws:secretsmanager:ap-northeast-2:000000000000:secret:inform-test"
    database_secret = {
        "host": "postgres.internal.test",
        "port": 5432,
        "dbname": "inform",
        "username": "inform_crawler",
        "password": "synthetic-password",
    }

    def _secret_client_factory(self, payload=None):
        client = Mock()
        client.get_secret_value.return_value = {
            "SecretString": json.dumps(payload or self.database_secret)
        }
        return Mock(return_value=client), client

    def test_resolves_only_the_approved_five_secret_fields(self):
        client_factory, client = self._secret_client_factory()

        actual = resolve_postgres_database_secret(self.secret_id, client_factory)

        self.assertEqual(actual, self.database_secret)
        client_factory.assert_called_once_with("secretsmanager")
        client.get_secret_value.assert_called_once_with(SecretId=self.secret_id)

    def test_rejects_missing_or_unapproved_secret_fields_without_echoing_values(self):
        malformed = dict(self.database_secret)
        malformed.pop("password")
        malformed["unexpected"] = "synthetic-extra"
        client_factory, _ = self._secret_client_factory(malformed)

        with self.assertRaises(DatabaseSecretConfigurationError) as raised:
            resolve_postgres_database_secret(self.secret_id, client_factory)

        self.assertNotIn("synthetic-password", str(raised.exception))
        self.assertNotIn("synthetic-extra", str(raised.exception))

    def test_retries_once_after_retryable_database_connection_failure(self):
        client_factory, client = self._secret_client_factory()
        connect = Mock(
            side_effect=[
                DatabaseConnectionRetryableError("synthetic connection failure"),
                "connection",
            ]
        )

        actual = connect_with_one_secret_refresh(
            self.secret_id, client_factory, connect
        )

        self.assertEqual(actual, "connection")
        self.assertEqual(client.get_secret_value.call_count, 2)
        self.assertEqual(connect.call_count, 2)

    def test_does_not_refresh_for_a_non_database_connection_failure(self):
        client_factory, client = self._secret_client_factory()
        connect = Mock(side_effect=RuntimeError("non-retryable"))

        with self.assertRaises(RuntimeError):
            connect_with_one_secret_refresh(self.secret_id, client_factory, connect)

        self.assertEqual(client.get_secret_value.call_count, 1)
        self.assertEqual(connect.call_count, 1)


if __name__ == "__main__":
    unittest.main()
