import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = (
    ROOT
    / ".agents"
    / "docs"
    / "contracts"
    / "v11-INFORM_CRAWLER_RUNTIME_RESULT_CONTRACT.md"
)
WORKER = (
    ROOT / "infra" / "aws" / "crawler" / "modules" / "spot" / "worker-command.sh.tftpl"
)


class RuntimeResultArtifactContractTests(unittest.TestCase):
    def test_versioned_contract_records_stable_exit_mapping(self):
        text = CONTRACT.read_text(encoding="utf-8")

        self.assertIn("v11-runtime-exit-1", text)
        for exit_code, error_class in (
            (65, "SCHEMA_CONTRACT_ERROR"),
            (70, "DETERMINISTIC_APPLICATION_ERROR"),
            (75, "DB_CONNECTION_TRANSIENT"),
            (77, "AUTHORIZATION_ERROR"),
            (78, "INVALID_CONFIGURATION"),
        ):
            with self.subTest(exit_code=exit_code):
                self.assertRegex(text, rf"(?m)^\| {exit_code} \| `{error_class}` \|")

    def test_worker_maps_exit_codes_without_log_parsing(self):
        text = WORKER.read_text(encoding="utf-8")

        self.assertIn("map_application_exit_code", text)
        self.assertIn("65) printf 'SCHEMA_CONTRACT_ERROR\\n'", text)
        self.assertIn("75) printf 'DB_CONNECTION_TRANSIENT\\n'", text)
        self.assertIn("77) printf 'AUTHORIZATION_ERROR\\n'", text)
        self.assertIn("78) printf 'INVALID_CONFIGURATION\\n'", text)
        self.assertNotRegex(
            text, r"grep.+(SCHEMA_CONTRACT|AUTHORIZATION|DB_CONNECTION)"
        )

    def test_failure_metadata_keeps_the_application_exit_code(self):
        text = WORKER.read_text(encoding="utf-8")

        self.assertIn('exit_code="$${3:-1}"', text)
        self.assertIn('--argjson exit_code "$exit_code"', text)
        self.assertIn("exit_code:$exit_code", text)
        self.assertIn(
            'persist_failure FAILED "$APPLICATION_ERROR_CLASS" "$CRAWLER_EXIT_CODE"',
            text,
        )


if __name__ == "__main__":
    unittest.main()
