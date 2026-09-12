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
    def test_docker_build_context_excludes_local_and_infrastructure_artifacts(
        self,
    ) -> None:
        dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
        entries = {
            line.strip().rstrip("/")
            for line in dockerignore.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        required_exclusions = {
            ".git",
            ".github",
            ".agents",
            ".specify",
            ".codex-*",
            ".playwright-mcp",
            "specs",
            "infra",
            ".env*",
            ".terraform",
            "*.tfstate*",
        }

        self.assertTrue(required_exclusions.issubset(entries))

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
            "harness/iam/README.md",
            "harness/iam/publisher-assume-role-policy.json",
            "harness/iam/render-dev-policies.ps1",
            "harness/iam/terraform-dev-role-trust-policy.json",
            "harness/iam/terraform-dev-role-permissions-policy.json",
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

    def test_environments_use_partial_s3_backend_with_native_lockfile(self) -> None:
        for environment in ("dev", "prod"):
            with self.subTest(environment=environment):
                versions = read(f"environments/{environment}/versions.tf")
                self.assertIn(
                    'required_version = ">= 1.10.0, < 2.0.0"',
                    versions,
                )
                backend = re.search(
                    r'backend\s+"s3"\s*\{(?P<body>.*?)\}',
                    versions,
                    re.DOTALL,
                )
                self.assertIsNotNone(backend)
                body = backend.group("body")
                self.assertRegex(body, r"\bencrypt\s*=\s*true")
                self.assertRegex(body, r"\buse_lockfile\s*=\s*true")
                for physical_setting in (
                    "bucket",
                    "key",
                    "region",
                    "profile",
                    "role_arn",
                ):
                    self.assertNotRegex(body, rf"\b{physical_setting}\s*=")

        readme = read("README.md")
        self.assertIn('-backend-config="bucket=<terraform-state-bucket>"', readme)
        self.assertIn("must not be the crawler durable-state bucket", readme)

    def test_environment_provider_lockfiles_are_committed_and_consistent(self) -> None:
        lockfiles = []
        for environment in ("dev", "prod"):
            with self.subTest(environment=environment):
                lockfile = (
                    IAC_ROOT / "environments" / environment / ".terraform.lock.hcl"
                )
                self.assertTrue(lockfile.is_file())
                content = lockfile.read_text(encoding="utf-8")
                self.assertIn('provider "registry.terraform.io/hashicorp/aws"', content)
                self.assertRegex(content, r'\bversion\s*=\s*"\d+\.\d+\.\d+"')
                lockfiles.append(content)

        self.assertEqual(lockfiles[0], lockfiles[1])
        gitignore_lines = {
            line.strip()
            for line in (REPO_ROOT / ".gitignore")
            .read_text(encoding="utf-8")
            .splitlines()
        }
        self.assertNotIn(".terraform.lock.hcl", gitignore_lines)

    def test_dev_terraform_role_handoff_is_scoped_and_template_only(self) -> None:
        publisher = json.loads(read("harness/iam/publisher-assume-role-policy.json"))
        trust = json.loads(read("harness/iam/terraform-dev-role-trust-policy.json"))
        permissions = json.loads(
            read("harness/iam/terraform-dev-role-permissions-policy.json")
        )

        self.assertEqual(
            publisher["Statement"],
            [
                {
                    "Sid": "AssumeInformCrawlerTerraformDevRole",
                    "Effect": "Allow",
                    "Action": "sts:AssumeRole",
                    "Resource": (
                        "arn:aws:iam::<AWS_ACCOUNT_ID>:role/"
                        "inform-crawler-terraform-dev"
                    ),
                }
            ],
        )
        self.assertEqual(
            trust["Statement"][0]["Principal"]["AWS"],
            "arn:aws:iam::<AWS_ACCOUNT_ID>:user/<ECR_PUBLISHER_USER_NAME>",
        )
        self.assertEqual(trust["Statement"][0]["Action"], "sts:AssumeRole")

        actions = {
            action
            for statement in permissions["Statement"]
            for action in (
                statement["Action"]
                if isinstance(statement["Action"], list)
                else [statement["Action"]]
            )
        }
        self.assertTrue(
            all(
                statement["Effect"] == "Allow" for statement in permissions["Statement"]
            )
        )
        for required_action in (
            "s3:GetObject",
            "s3:PutObject",
            "dynamodb:CreateTable",
            "iam:CreateRole",
            "iam:PassRole",
            "ec2:CreateLaunchTemplate",
            "ssm:CreateDocument",
            "states:CreateStateMachine",
            "scheduler:CreateSchedule",
        ):
            with self.subTest(required_action=required_action):
                self.assertIn(required_action, actions)
        self.assertNotIn("*", actions)
        self.assertNotIn("secretsmanager:GetSecretValue", actions)
        self.assertFalse(any(action.startswith("ecr:") for action in actions))

        rendered = json.dumps([publisher, trust, permissions])
        self.assertNotRegex(rendered, r"\b\d{12}\b")
        self.assertNotIn("-prod", rendered)
        readme = read("harness/iam/README.md")
        self.assertRegex(readme, r"must not be applied without\s+explicit approval")
        self.assertRegex(readme, r"do not commit rendered physical\s+identifiers")

    def test_dev_terraform_role_covers_provider_readback_actions(self) -> None:
        permissions = json.loads(
            read("harness/iam/terraform-dev-role-permissions-policy.json")
        )
        statements_by_sid = {
            statement["Sid"]: statement for statement in permissions["Statement"]
        }
        actions_by_sid = {
            statement["Sid"]: set(
                statement["Action"]
                if isinstance(statement["Action"], list)
                else [statement["Action"]]
            )
            for statement in permissions["Statement"]
        }

        self.assertIn(
            "ec2:CreateSecurityGroup",
            actions_by_sid["CreateTaggedDevCrawlerSecurityGroup"],
        )
        self.assertEqual(
            statements_by_sid["CreateTaggedDevCrawlerSecurityGroup"]["Resource"],
            "arn:aws:ec2:<AWS_REGION>:<AWS_ACCOUNT_ID>:security-group/*",
        )
        self.assertEqual(
            statements_by_sid["CreateDevCrawlerSecurityGroupInVpc"],
            {
                "Sid": "CreateDevCrawlerSecurityGroupInVpc",
                "Effect": "Allow",
                "Action": "ec2:CreateSecurityGroup",
                "Resource": "arn:aws:ec2:<AWS_REGION>:<AWS_ACCOUNT_ID>:vpc/<VPC_ID>",
            },
        )
        self.assertEqual(
            statements_by_sid["TagDevCrawlerSecurityGroupOnCreate"]["Condition"],
            {"StringEquals": {"ec2:CreateAction": "CreateSecurityGroup"}},
        )
        self.assertNotIn("CreateTaggedDevCrawlerEc2Resources", statements_by_sid)
        self.assertIn(
            "s3:GetBucketCORS",
            actions_by_sid["ManageDevCrawlerStateBucket"],
        )
        self.assertIn(
            "states:ListStateMachineVersions",
            actions_by_sid["ManageDevCrawlerStateMachine"],
        )

    def test_dev_policy_renderer_is_local_and_non_mutating(self) -> None:
        renderer = read("harness/iam/render-dev-policies.ps1")
        self.assertIn("aws sts get-caller-identity", renderer)
        self.assertNotRegex(renderer, r"\baws\s+(?:iam|s3|s3api|ec2)\b")
        self.assertIn("ConvertFrom-Json", renderer)
        self.assertIn("INFORM_TFSTATE_BUCKET", renderer)
        self.assertIn("INFORM_CRAWLER_STATE_BUCKET", renderer)
        self.assertIn("INFORM_VPC_ID", renderer)
        self.assertIn("INFORM_MAIN_DB_SG_ID", renderer)
        self.assertIn('Join-Path $PSScriptRoot "rendered"', renderer)

        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("infra/aws/crawler/harness/iam/rendered/", gitignore)

    def test_iam_outputs_are_unique(self) -> None:
        output_names = re.findall(r'output\s+"([^"]+)"', read("modules/iam/outputs.tf"))
        self.assertEqual(len(output_names), len(set(output_names)))

    def test_modules_do_not_use_deprecated_aws_region_name(self) -> None:
        for module in ("iam", "scheduler"):
            with self.subTest(module=module):
                self.assertNotIn(
                    "data.aws_region.current.name",
                    read(f"modules/{module}/main.tf"),
                )


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

    def test_tag_filtered_lifecycle_rule_does_not_abort_multipart_uploads(
        self,
    ) -> None:
        def lifecycle_rule(rule_id: str) -> str:
            id_position = self.state.index(f'id     = "{rule_id}"')
            block_start = self.state.rfind("  rule {", 0, id_position)
            depth = 0
            for match in re.finditer(r"[{}]", self.state[block_start:]):
                depth += 1 if match.group() == "{" else -1
                if depth == 0:
                    return self.state[block_start : block_start + match.end()]
            self.fail(f"Unclosed lifecycle rule: {rule_id}")

        queue_rule = lifecycle_rule("failure-queue-30-days")
        self.assertIn('tags   = { ArtifactClass = "queue" }', queue_rule)
        self.assertNotIn("abort_incomplete_multipart_upload", queue_rule)

        abort_rule = lifecycle_rule("abort-failure-multipart-uploads-7-days")
        self.assertIn('prefix = "${local.key_prefix}failures/"', abort_rule)
        self.assertIn(
            "abort_incomplete_multipart_upload { days_after_initiation = 7 }",
            abort_rule,
        )
        self.assertNotIn("tags", abort_rule)

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

    def test_worker_cleanup_reaps_background_sleep_children(self) -> None:
        worker = read("modules/spot/worker-command.sh.tftpl")
        for fragment in (
            "managed_sleep() {",
            "trap 'stop_background_process \"$${SLEEP_PID:-}\"; exit 0' TERM INT",
            'while managed_sleep "$HEARTBEAT_SECONDS"; do',
            "while managed_sleep 5; do",
            'stop_background_process "$HEARTBEAT_PID"',
            'stop_background_process "$INTERRUPTION_PID"',
            'stop_background_process "$WARNING_PID"',
            'stop_background_process "$TIMEOUT_PID"',
            'managed_timer "$WARNING_SECONDS" warning_action &',
            'managed_timer "$HARD_TIMEOUT_SECONDS" timeout_action &',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, worker)

        self.assertNotIn('(sleep "$WARNING_SECONDS";', worker)
        self.assertNotIn('(sleep "$HARD_TIMEOUT_SECONDS";', worker)
        self.assertNotIn('while sleep "$HEARTBEAT_SECONDS"; do', worker)
        self.assertNotIn("while sleep 5; do", worker)

    def test_worker_metadata_requests_have_bounded_runtime(self) -> None:
        worker = read("modules/spot/worker-command.sh.tftpl")
        self.assertEqual(2, worker.count("--connect-timeout 2"))
        self.assertEqual(2, worker.count("--max-time 5"))


class AwsSchedulerSpotTerraformContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scheduler = read("modules/scheduler/main.tf")
        cls.scheduler_outputs = read("modules/scheduler/outputs.tf")
        cls.scheduler_definition_template = read(
            "modules/scheduler/state-machine.asl.json"
        )
        rendered_definition = (
            cls.scheduler_definition_template.replace(
                "${launch_template_id}", "lt-approved"
            )
            .replace("${launch_template_version}", "7")
            .replace(
                "${fleet_overrides_json}",
                '[{"InstanceType":"m7i-flex.large","SubnetId":"subnet-approved"}]',
            )
        )
        cls.scheduler_definition = json.loads(rendered_definition)
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

    def test_instant_fleet_keeps_multi_pool_fallback_valid(self) -> None:
        launch = self.scheduler_definition["States"]["LaunchSpotWorker"]
        spot_options = launch["Parameters"]["SpotOptions"]

        self.assertEqual("price-capacity-optimized", spot_options["AllocationStrategy"])
        self.assertFalse(spot_options["SingleInstanceType"])
        self.assertFalse(spot_options["SingleAvailabilityZone"])
        self.assertNotIn("MinTargetCapacity", spot_options)

    def test_create_fleet_permission_is_separate_from_launch_constraints(
        self,
    ) -> None:
        create_fleet = re.search(
            r'sid\s*=\s*"CreateApprovedWorkerFleet"[\s\S]*?^\s*}',
            self.scheduler,
            re.MULTILINE,
        )
        self.assertIsNotNone(create_fleet)
        create_fleet_block = create_fleet.group(0)
        self.assertRegex(
            create_fleet_block,
            r'actions\s*=\s*\["ec2:CreateFleet"\]',
        )
        self.assertIn(':fleet/*"', create_fleet_block)
        self.assertIn("var.launch_template_arn", create_fleet_block)
        self.assertIn("local.subnet_arns", create_fleet_block)
        self.assertIn(':instance/*"', create_fleet_block)
        self.assertIn(':volume/*"', create_fleet_block)
        self.assertIn('::image/*"', create_fleet_block)
        self.assertNotIn("ec2:LaunchTemplate", create_fleet_block)
        self.assertNotIn("ec2:Subnet", create_fleet_block)
        self.assertNotIn("ec2:InstanceType", create_fleet_block)

        run_template = re.search(
            r'sid\s*=\s*"RunOnlyApprovedWorkerTemplate"[\s\S]*?'
            r'^\s{2}}(?=\n\n\s{2}statement\s*{)',
            self.scheduler,
            re.MULTILINE,
        )
        self.assertIsNotNone(run_template)
        run_template_block = run_template.group(0)
        self.assertRegex(
            run_template_block,
            r'actions\s*=\s*\["ec2:RunInstances"\]',
        )
        self.assertIn('variable = "ec2:LaunchTemplate"', run_template_block)
        self.assertIn(
            'variable = "ec2:IsLaunchTemplateResource"', run_template_block
        )
        self.assertIn('test     = "Bool"', run_template_block)
        self.assertIn('values   = ["true"]', run_template_block)
        self.assertIn(':launch-template/*"', run_template_block)
        self.assertRegex(
            self.scheduler,
            r'sid\s*=\s*"UseOnlyApprovedWorkerLaunchTemplate"[\s\S]*?'
            r'resources\s*=\s*\[var\.launch_template_arn\]',
        )
        self.assertRegex(
            self.scheduler,
            r'sid\s*=\s*"RunOnlyApprovedWorkerInstanceTypes"[\s\S]*?'
            r'variable\s*=\s*"ec2:InstanceType"',
        )
        self.assertRegex(
            self.scheduler,
            r'sid\s*=\s*"RunOnlyApprovedWorkerSubnets"[\s\S]*?'
            r"resources\s*=\s*local\.subnet_arns[\s\S]*?"
            r'variable\s*=\s*"ec2:LaunchTemplate"',
        )
        self.assertRegex(
            self.scheduler,
            r'sid\s*=\s*"RunOnlyApprovedWorkerNetworkInterfaces"[\s\S]*?'
            r'variable\s*=\s*"ec2:Subnet"',
        )

    def test_launch_configuration_is_rendered_from_terraform_not_execution_input(
        self,
    ) -> None:
        self.assertIn(
            'definition = templatefile("${path.module}/state-machine.asl.json"',
            self.scheduler,
        )
        for assignment in (
            "launch_template_id      = var.launch_template_id",
            "launch_template_version = tostring(var.launch_template_version)",
            "fleet_overrides_json    = jsonencode(local.fleet_overrides)",
        ):
            with self.subTest(assignment=assignment):
                self.assertIn(assignment, self.scheduler)

        for dynamic_field in (
            '"LaunchTemplateId.$"',
            '"LaunchTemplateVersion.$"',
            '"Version.$"',
            '"Overrides.$"',
        ):
            with self.subTest(dynamic_field=dynamic_field):
                self.assertNotIn(
                    dynamic_field, self.scheduler_definition_template
                )

        launch_config = self.scheduler_definition["States"]["LaunchSpotWorker"][
            "Parameters"
        ]["LaunchTemplateConfigs"][0]
        self.assertEqual(
            {"LaunchTemplateId": "lt-approved", "Version": "7"},
            launch_config["LaunchTemplateSpecification"],
        )
        self.assertEqual(
            [
                {
                    "InstanceType": "m7i-flex.large",
                    "SubnetId": "subnet-approved",
                }
            ],
            launch_config["Overrides"],
        )

        schedule_target = re.search(
            r'target\s*\{[\s\S]*?input\s*=\s*jsonencode\(\{([\s\S]*?)\}\)',
            self.scheduler,
        )
        self.assertIsNotNone(schedule_target)
        manual_input = re.search(
            r'output\s+"manual_execution_input"\s*\{[\s\S]*?jsonencode\(\{'
            r'([\s\S]*?)\}\)',
            self.scheduler_outputs,
        )
        self.assertIsNotNone(manual_input)
        for input_block in (schedule_target.group(1), manual_input.group(1)):
            self.assertNotIn("LaunchTemplateId", input_block)
            self.assertNotIn("LaunchTemplateVersion", input_block)
            self.assertNotIn("Overrides", input_block)

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

    def test_launch_authorization_failure_is_non_retryable(self) -> None:
        states = self.scheduler_definition["States"]
        launch_catch = states["LaunchSpotWorker"]["Catch"][0]
        self.assertEqual("ClassifyLaunchFailure", launch_catch["Next"])

        authorization_targets = {
            choice["Next"]
            for choice in states["ClassifyLaunchFailure"]["Choices"]
            if "authorized" in choice.get("StringMatches", "").lower()
            or "accessdenied" in choice.get("StringMatches", "").lower()
            or "unauthorized" in choice.get("StringMatches", "").lower()
        }
        self.assertEqual({"SetAuthorizationFailure"}, authorization_targets)
        self.assertEqual(
            "AUTHORIZATION_ERROR",
            states["SetAuthorizationFailure"]["Result"]["Value"]["error_class"],
        )
        self.assertEqual("Failed", states["SetAuthorizationFailure"]["Next"])

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
