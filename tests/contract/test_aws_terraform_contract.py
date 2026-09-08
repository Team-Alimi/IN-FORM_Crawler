"""Static contract tests for the approved AWS crawler Terraform source.

These tests intentionally do not initialize Terraform providers or contact AWS.
The real dev-harness acceptance run remains a separately approved operation.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IAC_ROOT = REPO_ROOT / "infra" / "aws" / "crawler"


def read(relative_path: str) -> str:
    return (IAC_ROOT / relative_path).read_text(encoding="utf-8")


class AwsTerraformLayoutContractTests(unittest.TestCase):
    def test_owner_approved_tree_is_present(self) -> None:
        required_paths = (
            "README.md",
            "modules/state/main.tf",
            "modules/iam/main.tf",
            "modules/network/main.tf",
            "modules/spot/main.tf",
            "modules/scheduler/main.tf",
            "environments/dev/main.tf",
            "environments/prod/main.tf",
            "harness/README.md",
            "harness/run-dev.ps1",
        )

        for relative_path in required_paths:
            with self.subTest(path=relative_path):
                self.assertTrue((IAC_ROOT / relative_path).is_file())

    def test_environment_inputs_are_parameterized(self) -> None:
        variables = read("environments/dev/variables.tf")
        for name in (
            "region",
            "vpc_id",
            "subnet_ids",
            "crawler_security_group_id",
            "main_db_security_group_id",
            "candidate_instance_types",
            "state_bucket_name",
            "state_prefix",
            "parameter_store_namespace",
            "ami_id",
            "crawler_image_ref",
            "crawler_ecr_repository_arn",
        ):
            with self.subTest(variable=name):
                self.assertRegex(variables, rf'variable\s+"{name}"')

    def test_iam_outputs_are_unique(self) -> None:
        output_names = re.findall(r'output\s+"([^"]+)"', read("modules/iam/outputs.tf"))
        self.assertEqual(len(output_names), len(set(output_names)))


class AwsDurableStateTerraformContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.state = read("modules/state/main.tf")

    def test_state_bucket_is_private_versioned_and_sse_s3(self) -> None:
        for fragment in (
            'resource "aws_s3_bucket_public_access_block"',
            "block_public_acls       = true",
            "block_public_policy     = true",
            "ignore_public_acls      = true",
            "restrict_public_buckets = true",
            'status = "Enabled"',
            'sse_algorithm = "AES256"',
            "aws:SecureTransport",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.state)

    def test_state_lifecycle_matches_v11(self) -> None:
        expected_retention = {
            "history-runs-90-days": "90",
            "success-logs-30-days": "30",
            "failure-artifacts-90-days": "90",
            "failure-queue-30-days": "30",
        }
        for rule_id, days in expected_retention.items():
            with self.subTest(rule=rule_id):
                self.assertRegex(
                    self.state,
                    rf'id\s*=\s*"{rule_id}"[\s\S]*?days\s*=\s*{days}',
                )

        self.assertNotRegex(self.state, r'prefix\s*=\s*"history/current')

    def test_lock_table_uses_atomic_lease_data_not_ttl_takeover(self) -> None:
        self.assertIn('resource "aws_dynamodb_table" "runtime_lock"', self.state)
        self.assertIn('hash_key     = "lock_key"', self.state)
        self.assertIn('billing_mode = "PAY_PER_REQUEST"', self.state)
        self.assertNotRegex(self.state, r"(?m)^\s*ttl\s*\{")

    def test_worker_transport_preserves_publication_and_fencing_order(self) -> None:
        worker = read("modules/spot/worker-command.sh.tftpl")
        for fragment in (
            "readonly LEASE_SECONDS=1200",
            "readonly HEARTBEAT_SECONDS=300",
            "readonly WARNING_SECONDS=5400",
            "readonly HARD_TIMEOUT_SECONDS=7200",
            "attribute_not_exists(lock_key) OR lease_expires_at < :now",
            "generation=if_not_exists(generation,:zero)+:one",
            "owns_live_lease || return 1",
            "history/runs/$RUN_ID/",
            "history/current/$RUN_ID/",
            "history/current.json",
            "--if-match",
            "--if-none-match",
            "_SUCCESS",
            'rm -rf "$QUEUE_DIR"/*',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, worker)

        run_success = worker.index('key "$${run_prefix}_SUCCESS"')
        current_success = worker.index('key "$${current_prefix}_SUCCESS"')
        current_pointer = worker.index(
            'key "$${STATE_PREFIX}history/current.json"', current_success
        )
        self.assertLess(run_success, current_success)
        self.assertLess(current_success, current_pointer)


class AwsSchedulerSpotTerraformContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scheduler = read("modules/scheduler/main.tf")
        cls.scheduler_definition = json.loads(
            read("modules/scheduler/state-machine.asl.json")
        )
        cls.spot = read("modules/spot/main.tf")
        cls.network = read("modules/network/main.tf")
        cls.iam = read("modules/iam/main.tf")

    def test_schedule_and_retry_constants_match_contract(self) -> None:
        self.assertIn(
            'schedule_expression          = "cron(0 6 * * ? *)"', self.scheduler
        )
        self.assertIn('schedule_expression_timezone = "Asia/Seoul"', self.scheduler)
        self.assertRegex(
            self.scheduler,
            r'state\s*=\s*var\.schedule_enabled\s*\?\s*"ENABLED"\s*:\s*"DISABLED"',
        )

        definition = json.dumps(self.scheduler_definition, sort_keys=True)
        self.assertIn('"Seconds": 600', definition)
        self.assertIn('"Seconds": 1800', definition)
        self.assertIn('"TimeoutSeconds": 7200', definition)
        self.assertIn('"NumericGreaterThanEquals": 240', definition)
        self.assertIn('"NumericGreaterThanEquals": 180', definition)
        self.assertIn('"NumericGreaterThanEquals": 3', definition)
        self.assertIn("SKIPPED_OVERLAP", definition)
        for retryable in (
            "SPOT_CAPACITY",
            "SPOT_INTERRUPTION",
            "BOOTSTRAP_TRANSIENT",
            "DB_CONNECTION_TRANSIENT",
            "S3_TRANSIENT",
        ):
            with self.subTest(error_class=retryable):
                self.assertIn(retryable, definition)

    def test_state_machine_references_only_declared_states(self) -> None:
        states = self.scheduler_definition["States"]
        targets: set[str] = set()
        for state in states.values():
            if "Next" in state:
                targets.add(state["Next"])
            for choice in state.get("Choices", []):
                if "Next" in choice:
                    targets.add(choice["Next"])
            for catcher in state.get("Catch", []):
                targets.add(catcher["Next"])
        self.assertEqual(set(), targets - set(states))
        self.assertIn(self.scheduler_definition["StartAt"], states)

    def test_spot_worker_is_disposable_and_multi_pool(self) -> None:
        for fragment in (
            'instance_interruption_behavior = "terminate"',
            'allocation_strategy = "price-capacity-optimized"',
            "delete_on_termination = true",
            'instance_initiated_shutdown_behavior = "terminate"',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.spot)

        variables = read("modules/spot/variables.tf")
        self.assertIn("length(var.subnet_ids) >= 2", variables)
        self.assertIn("length(var.candidate_instance_types) >= 2", variables)

    def test_network_has_no_ingress_and_private_db_rule(self) -> None:
        self.assertNotIn(
            'resource "aws_vpc_security_group_ingress_rule" "crawler"', self.network
        )
        self.assertIn(
            'resource "aws_vpc_security_group_ingress_rule" "postgres_from_crawler"',
            self.network,
        )
        self.assertIn("from_port                    = 5432", self.network)
        self.assertIn("to_port                      = 5432", self.network)
        self.assertRegex(self.network, r'cidr_ipv4\s*=\s*"0\.0\.0\.0/0"')

    def test_runtime_and_control_plane_iam_are_separate(self) -> None:
        for fragment in (
            'resource "aws_iam_role" "runtime"',
            'resource "aws_iam_role" "orchestration"',
            'resource "aws_iam_role" "scheduler"',
            'actions   = ["iam:PassRole"]',
            "resources = [aws_iam_role.runtime.arn]",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.iam)

    def test_runtime_ecr_pull_is_repository_scoped_and_ephemeral(self) -> None:
        self.assertRegex(
            self.iam,
            r'sid\s*=\s*"GetEcrAuthorizationToken"[\s\S]*?'
            r'actions\s*=\s*\["ecr:GetAuthorizationToken"\][\s\S]*?'
            r'resources\s*=\s*\["\*"\]',
        )
        for action in (
            "ecr:BatchCheckLayerAvailability",
            "ecr:BatchGetImage",
            "ecr:GetDownloadUrlForLayer",
        ):
            with self.subTest(action=action):
                self.assertIn(action, self.iam)
        self.assertIn("resources = [var.crawler_ecr_repository_arn]", self.iam)

        worker = read("modules/spot/worker-command.sh.tftpl")
        for fragment in (
            "readonly AWS_REGION='${aws_region}'",
            'export DOCKER_CONFIG="$ROOT_DIR/docker-config"',
            'aws ecr get-login-password --region "$AWS_REGION"',
            'docker login --username AWS --password-stdin "$registry"',
            'docker pull "$CRAWLER_IMAGE_REF"',
            'docker logout "$registry"',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, worker)

        self.assertNotRegex(
            self.iam,
            re.compile(r'(?s)resource\s+"aws_iam_role_policy"\s+"runtime".*?"ec2:\*"'),
        )
        self.assertIn('actions   = ["secretsmanager:GetSecretValue"]', self.iam)
        self.assertIn("resources = [var.database_secret_arn]", self.iam)


class AwsDevHarnessContractTests(unittest.TestCase):
    def test_harness_requires_explicit_dev_identity_and_never_targets_prod(
        self,
    ) -> None:
        harness = read("harness/run-dev.ps1")
        for guard in (
            "$ExpectedAccountId",
            "$ExpectedRegion",
            "$DevStateBucket",
            "$DevLockTable",
            "$DevStateMachineArn",
            "$DevDbGuardParameter",
            "GetCallerIdentity",
            "inform-crawler-state-dev",
            "inform-crawler-runtime-lock-dev",
            "inform-crawler-scheduler-dev",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard, harness)

        self.assertIn("PRODUCTION_DB_ACCESS_ALLOWED", harness)
        self.assertIn("Assert-False", harness)
        self.assertNotRegex(
            harness, r'(?i)(password|token|secret)\s*=\s*["\'][^"\']+["\']'
        )

    def test_each_harness_scenario_runs_once_with_consistent_timeout_result(
        self,
    ) -> None:
        harness = read("harness/run-dev.ps1")
        self.assertEqual(
            1,
            len(re.findall(r"(?m)^Assert-DevInfrastructure\s*$", harness)),
        )
        for scenario in (
            "Success",
            "Overlap",
            "LockExpiry",
            "Heartbeat",
            "TransientRetry",
            "Timeout",
            "SpotInterruption",
            "CapacityFallback",
            "All",
        ):
            with self.subTest(scenario=scenario):
                self.assertEqual(
                    1,
                    len(
                        re.findall(
                            rf"(?m)^\s*'{scenario}'\s*\{{",
                            harness,
                        )
                    ),
                )
        self.assertIn("Assert-ExecutionFailed -Simulation 'TIMEOUT'", harness)
        self.assertNotIn("Assert-ExecutionSucceeded -Simulation 'TIMEOUT'", harness)


if __name__ == "__main__":
    unittest.main()
