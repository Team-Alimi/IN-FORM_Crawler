"""Offline contract tests for the local dev-plan coordinator."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
COORDINATOR_PATH = REPO_ROOT / ".codex-dev-plan-coordinator.py"


def load_coordinator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "dev_plan_coordinator_under_test", COORDINATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the dev-plan coordinator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DevPlanCoordinatorHarnessFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator = load_coordinator()

    def test_classifies_daily_crawler_precondition_rejection(self) -> None:
        output = (
            "An error occurred (ConditionalCheckFailedException) when calling "
            "the UpdateItem operation"
        )

        category = self.coordinator.classify_harness_failure(output)

        self.assertEqual(category, "LEASE_PRECONDITION_REJECTED")

    def test_classifies_live_worker_lease_contract_mismatch(self) -> None:
        output = (
            "Live worker document is missing the lease contract fragment "
            "'owner_run_id=:owner AND generation=:generation'."
        )

        category = self.coordinator.classify_harness_failure(output)

        self.assertEqual(category, "LIVE_LEASE_CONTRACT_MISMATCH")

    def test_classifies_invalid_live_lease_context(self) -> None:
        output = "ExecutionInputJson does not identify the worker document."

        category = self.coordinator.classify_harness_failure(output)

        self.assertEqual(category, "LIVE_LEASE_CONTEXT_INVALID")

    def test_classifies_powershell_runtime_failure_without_echoing_details(
        self,
    ) -> None:
        output = "A parameter cannot be found that matches parameter name 'Example'."

        category = self.coordinator.classify_harness_failure(output)

        self.assertEqual(category, "POWERSHELL_RUNTIME_ERROR")
        self.assertNotIn("Example", category)

    def test_classifies_credential_safety_deadline(self) -> None:
        output = (
            "HARNESS_STAGE name=CredentialSafetyStop\n"
            "Dev harness stopped execution before temporary role credentials expire."
        )

        category = self.coordinator.classify_harness_failure(output)

        self.assertEqual(category, "CREDENTIAL_SAFETY_DEADLINE")

    def test_reports_only_the_last_allowlisted_harness_stage(self) -> None:
        output = "\n".join(
            (
                "HARNESS_STAGE name=DevInfrastructure",
                "HARNESS_STAGE name=DevStateBucket",
                "HARNESS_STAGE name=LiveLeaseContract",
                "HARNESS_STAGE name=LeasePrecondition",
            )
        )

        stage = self.coordinator.harness_failure_stage(output)

        self.assertEqual(stage, "LeasePrecondition")

    def test_reports_allowlisted_dev_infrastructure_substage(self) -> None:
        output = "\n".join(
            (
                "HARNESS_STAGE name=DevInfrastructure",
                "HARNESS_STAGE name=DevIdentity",
                "HARNESS_STAGE name=DevNaming",
                "HARNESS_STAGE name=DevDbGuard",
                "HARNESS_STAGE name=DevStateBucket",
            )
        )

        stage = self.coordinator.harness_failure_stage(output)

        self.assertEqual(stage, "DevStateBucket")

    def test_rejects_unrecognized_harness_stage_text(self) -> None:
        output = "HARNESS_STAGE name=credential-value-that-must-not-be-emitted"

        stage = self.coordinator.harness_failure_stage(output)

        self.assertEqual(stage, "UNKNOWN")


class DevPlanCoordinatorCredentialLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator = load_coordinator()

    def test_assume_role_retains_expiration_as_non_environment_metadata(
        self,
    ) -> None:
        responses = (
            {
                "Credentials": {
                    "AccessKeyId": "fake-role-access",
                    "SecretAccessKey": "fake-role-secret",
                    "SessionToken": "fake-role-session",
                    "Expiration": "2030-01-01T00:00:00+00:00",
                }
            },
            {
                "Account": self.coordinator.EXPECTED_ACCOUNT,
                "Arn": (
                    "arn:aws:sts::869190334503:assumed-role/"
                    "inform-crawler-terraform-dev/test"
                ),
            },
        )

        with mock.patch.object(self.coordinator, "aws_json", side_effect=responses):
            credentials = self.coordinator.assume_role(
                "fake-access", "fake-secret", "fake-session"
            )

        expiration_key = self.coordinator.ROLE_CREDENTIAL_EXPIRATION_KEY
        self.assertGreater(int(credentials[expiration_key]), int(time.time()))
        environment = self.coordinator.safe_environment(credentials)
        self.assertNotIn(expiration_key, environment)
        self.assertEqual(environment["AWS_ACCESS_KEY_ID"], "fake-role-access")

    def test_parent_cleanup_stops_only_matching_running_harness_executions(
        self,
    ) -> None:
        matching_arn = (
            "arn:aws:states:ap-northeast-2:869190334503:execution:"
            "inform-crawler-orchestration-dev:harness-run123-live"
        )
        other_arn = (
            "arn:aws:states:ap-northeast-2:869190334503:execution:"
            "inform-crawler-orchestration-dev:harness-other-live"
        )
        responses = (
            {
                "executions": [
                    {"name": "harness-run123-live", "executionArn": matching_arn},
                    {"name": "harness-other-live", "executionArn": other_arn},
                ]
            },
            {},
        )

        with mock.patch.object(
            self.coordinator, "aws_json", side_effect=responses
        ) as aws_json:
            stopped = self.coordinator.stop_matching_harness_executions(
                {
                    "AWS_ACCESS_KEY_ID": "fake-role-access",
                    "AWS_SECRET_ACCESS_KEY": "fake-role-secret",
                    "AWS_SESSION_TOKEN": "fake-role-session",
                },
                "arn:aws:states:ap-northeast-2:869190334503:stateMachine:"
                "inform-crawler-orchestration-dev",
                "run123",
            )

        self.assertEqual(stopped, 1)
        self.assertEqual(aws_json.call_count, 2)
        stop_arguments = aws_json.call_args_list[1].args[0]
        self.assertEqual(stop_arguments[:2], ["stepfunctions", "stop-execution"])
        self.assertIn(matching_arn, stop_arguments)
        self.assertNotIn(other_arn, stop_arguments)

    def test_parent_cleanup_attempts_every_matching_execution_after_failure(
        self,
    ) -> None:
        prefix = (
            "arn:aws:states:ap-northeast-2:869190334503:execution:"
            "inform-crawler-orchestration-dev:"
        )
        responses = (
            {
                "executions": [
                    {
                        "name": "harness-run123-first",
                        "executionArn": prefix + "harness-run123-first",
                    },
                    {
                        "name": "harness-run123-second",
                        "executionArn": prefix + "harness-run123-second",
                    },
                ]
            },
            RuntimeError("NETWORK_ERROR"),
            {},
        )

        with (
            mock.patch.object(
                self.coordinator, "aws_json", side_effect=responses
            ) as aws_json,
            self.assertRaisesRegex(RuntimeError, "HARNESS_EXECUTION_STOP_FAILED"),
        ):
            self.coordinator.stop_matching_harness_executions(
                {
                    "AWS_ACCESS_KEY_ID": "fake-role-access",
                    "AWS_SECRET_ACCESS_KEY": "fake-role-secret",
                    "AWS_SESSION_TOKEN": "fake-role-session",
                },
                "arn:aws:states:ap-northeast-2:869190334503:stateMachine:"
                "inform-crawler-orchestration-dev",
                "run123",
            )

        self.assertEqual(aws_json.call_count, 3)


class DevPlanCoordinatorCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator = load_coordinator()

    def _patch_harness_dependencies(
        self, stack: ExitStack, *, scenario_succeeds: bool
    ) -> None:
        coordinator = self.coordinator
        stack.enter_context(
            mock.patch.object(
                coordinator,
                "serve_credentials",
                return_value=("fake-access", "fake-secret", "fake-session"),
            )
        )
        stack.enter_context(
            mock.patch.object(
                coordinator,
                "assume_role",
                return_value={
                    "AWS_ACCESS_KEY_ID": "fake-role-access",
                    "AWS_SECRET_ACCESS_KEY": "fake-role-secret",
                    "AWS_SESSION_TOKEN": "fake-role-session",
                },
            )
        )
        stack.enter_context(
            mock.patch.object(coordinator, "pull_remote_state", return_value={})
        )
        stack.enter_context(
            mock.patch.object(coordinator, "derive_harness_context", return_value={})
        )
        stack.enter_context(
            mock.patch.object(coordinator, "list_dev_workers", return_value={})
        )
        stack.enter_context(
            mock.patch.object(
                coordinator,
                "run_harness_scenario",
                return_value=scenario_succeeds,
            )
        )
        stack.enter_context(
            mock.patch.object(
                coordinator,
                "cleanup_new_workers",
                side_effect=RuntimeError("HARNESS_CLEANUP_TIMEOUT"),
            )
        )
        stack.enter_context(mock.patch.object(coordinator, "emit"))

    def test_main_harness_cleanup_failure_changes_success_to_failure(self) -> None:
        with TemporaryDirectory() as directory, ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    self.coordinator,
                    "STATUS_PATH",
                    Path(directory) / "status.log",
                )
            )
            self._patch_harness_dependencies(stack, scenario_succeeds=True)

            result = self.coordinator.main_harness(["Success"])

        self.assertNotEqual(result, 0)

    def test_main_harness_cleanup_failure_preserves_work_failure(self) -> None:
        with TemporaryDirectory() as directory, ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    self.coordinator,
                    "STATUS_PATH",
                    Path(directory) / "status.log",
                )
            )
            self._patch_harness_dependencies(stack, scenario_succeeds=False)

            result = self.coordinator.main_harness(["Success"])

        self.assertEqual(result, 5)

    def _patch_release_dependencies(
        self, stack: ExitStack, *, scenario_succeeds: bool
    ) -> None:
        self._patch_harness_dependencies(stack, scenario_succeeds=scenario_succeeds)
        coordinator = self.coordinator
        stack.enter_context(
            mock.patch.object(
                coordinator,
                "publish_image",
                return_value=("fake-image", "fake-repository", "fake-sha"),
            )
        )
        stack.enter_context(
            mock.patch.object(coordinator, "execute_plan", return_value=True)
        )
        stack.enter_context(
            mock.patch.object(coordinator, "await_control", return_value="apply")
        )
        stack.enter_context(
            mock.patch.object(coordinator, "execute_apply", return_value=True)
        )
        stack.enter_context(mock.patch.object(coordinator, "cleanup_volume"))

    def test_main_release_cleanup_failure_changes_success_to_failure(self) -> None:
        with TemporaryDirectory() as directory, ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    self.coordinator,
                    "STATUS_PATH",
                    Path(directory) / "status.log",
                )
            )
            self._patch_release_dependencies(stack, scenario_succeeds=True)

            result = self.coordinator.main_release()

        self.assertNotEqual(result, 0)

    def test_main_release_cleanup_failure_preserves_work_failure(self) -> None:
        with TemporaryDirectory() as directory, ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    self.coordinator,
                    "STATUS_PATH",
                    Path(directory) / "status.log",
                )
            )
            self._patch_release_dependencies(stack, scenario_succeeds=False)

            result = self.coordinator.main_release()

        self.assertEqual(result, 5)

    def test_main_release_volume_cleanup_failure_changes_success_to_failure(
        self,
    ) -> None:
        with TemporaryDirectory() as directory, ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    self.coordinator,
                    "STATUS_PATH",
                    Path(directory) / "status.log",
                )
            )
            self._patch_release_dependencies(stack, scenario_succeeds=True)
            stack.enter_context(
                mock.patch.object(
                    self.coordinator, "cleanup_new_workers", return_value=None
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.coordinator,
                    "cleanup_volume",
                    side_effect=RuntimeError("PLAN_VOLUME_REMOVE_FAILED"),
                )
            )

            result = self.coordinator.main_release()

        self.assertNotEqual(result, 0)

    def test_volume_remove_failure_is_reported_and_retains_retry_state(self) -> None:
        coordinator = self.coordinator
        original_name = coordinator.VOLUME_NAME
        original_created = coordinator._volume_created
        try:
            coordinator.VOLUME_NAME = "codex-inform-crawler-dev-plan-0123456789abcdef"
            coordinator._volume_created = True
            failed = self.coordinator.subprocess.CompletedProcess(
                args=["docker", "volume", "rm"],
                returncode=1,
                stdout="",
                stderr="remove failed",
            )
            with (
                mock.patch.object(coordinator.shutil, "which", return_value="docker"),
                mock.patch.object(coordinator, "run_quiet", return_value=failed),
            ):
                with self.assertRaisesRegex(RuntimeError, "PLAN_VOLUME_REMOVE_FAILED"):
                    coordinator.cleanup_volume()
            self.assertTrue(coordinator._volume_created)
        finally:
            coordinator.VOLUME_NAME = original_name
            coordinator._volume_created = original_created

    def test_main_release_clears_source_credentials_before_plan(self) -> None:
        captured: dict[str, object] = {}
        role_credentials = {
            "AWS_ACCESS_KEY_ID": "fake-role-access",
            "AWS_SECRET_ACCESS_KEY": "fake-role-secret",
            "AWS_SESSION_TOKEN": "fake-role-session",
        }

        def publish_image(credentials: dict[str, str]) -> tuple[str, str, str]:
            captured["source_credentials"] = credentials
            return "fake-image", "fake-repository", "fake-sha"

        def execute_plan(
            credentials: dict[str, str],
            _variables: dict[str, str],
            _allowed_updates: set[str] | None,
        ) -> bool:
            source_credentials = captured["source_credentials"]
            self.assertIsInstance(source_credentials, dict)
            captured["source_at_plan"] = dict(source_credentials)
            captured["role_at_plan"] = dict(credentials)
            return False

        with TemporaryDirectory() as directory, ExitStack() as stack:
            coordinator = self.coordinator
            stack.enter_context(
                mock.patch.object(
                    coordinator,
                    "STATUS_PATH",
                    Path(directory) / "status.log",
                )
            )
            stack.enter_context(
                mock.patch.object(
                    coordinator,
                    "serve_credentials",
                    return_value=("fake-access", "fake-secret", "fake-session"),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    coordinator, "publish_image", side_effect=publish_image
                )
            )
            stack.enter_context(
                mock.patch.object(
                    coordinator,
                    "assume_role",
                    return_value=role_credentials,
                )
            )
            stack.enter_context(
                mock.patch.object(coordinator, "execute_plan", side_effect=execute_plan)
            )
            stack.enter_context(mock.patch.object(coordinator, "cleanup_volume"))
            stack.enter_context(mock.patch.object(coordinator, "emit"))

            result = coordinator.main_release()

        self.assertEqual(result, 2)
        self.assertEqual(captured["source_at_plan"], {})
        self.assertEqual(
            captured["role_at_plan"],
            {
                "AWS_ACCESS_KEY_ID": "fake-role-access",
                "AWS_SECRET_ACCESS_KEY": "fake-role-secret",
                "AWS_SESSION_TOKEN": "fake-role-session",
            },
        )


class DevPlanCoordinatorApprovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator = load_coordinator()

    def test_credential_bearer_is_console_only_and_expires_after_submission(
        self,
    ) -> None:
        token = "fake-one-time-credential-token"
        output = io.StringIO()
        result: dict[str, tuple[str, str, str]] = {}
        errors: list[BaseException] = []

        with TemporaryDirectory() as directory:
            status_path = Path(directory) / "status.log"

            def await_credentials() -> None:
                try:
                    result["credentials"] = self.coordinator.serve_credentials(
                        "test credential form"
                    )
                except BaseException as error:  # pragma: no cover - surfaced below
                    errors.append(error)

            with (
                mock.patch.object(self.coordinator, "STATUS_PATH", status_path),
                mock.patch.object(
                    self.coordinator.secrets,
                    "token_urlsafe",
                    return_value=token,
                ),
                contextlib.redirect_stdout(output),
            ):
                thread = threading.Thread(target=await_credentials, daemon=True)
                thread.start()
                deadline = time.monotonic() + 5
                while "CREDENTIAL_FORM_URL=" not in output.getvalue():
                    if time.monotonic() >= deadline:
                        self.fail("Credential URL was not shown")
                    time.sleep(0.01)

                console_line = next(
                    line
                    for line in output.getvalue().splitlines()
                    if line.startswith("CREDENTIAL_FORM_URL=")
                )
                form_url = console_line.removeprefix("CREDENTIAL_FORM_URL=")
                submit_url = form_url.replace("/?token=", "/submit?token=")
                request = urllib.request.Request(
                    submit_url,
                    data=(
                        b"access_key=fake-access&secret_key=fake-secret"
                        b"&session_token=fake-session"
                    ),
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    self.assertEqual(response.status, 200)
                thread.join(timeout=5)

            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(
                result["credentials"],
                ("fake-access", "fake-secret", "fake-session"),
            )
            self.assertIn(form_url, output.getvalue())
            self.assertIn(token, output.getvalue())
            persisted = (
                status_path.read_text(encoding="utf-8") if status_path.exists() else ""
            )
            self.assertNotIn(form_url, persisted)
            self.assertNotIn(token, persisted)

            with self.assertRaises(urllib.error.URLError):
                urllib.request.urlopen(request, timeout=1)

    def test_apply_bearer_is_console_only_and_expires_after_selection(self) -> None:
        token = "fake-one-time-approval-token"
        output = io.StringIO()
        result: dict[str, str] = {}
        errors: list[BaseException] = []

        with TemporaryDirectory() as directory:
            status_path = Path(directory) / "status.log"

            def await_approval() -> None:
                try:
                    result["command"] = self.coordinator.await_control(
                        {"apply", "cancel"}
                    )
                except BaseException as error:  # pragma: no cover - surfaced below
                    errors.append(error)

            with (
                mock.patch.object(self.coordinator, "STATUS_PATH", status_path),
                mock.patch.object(
                    self.coordinator.secrets,
                    "token_urlsafe",
                    return_value=token,
                ),
                contextlib.redirect_stdout(output),
            ):
                thread = threading.Thread(target=await_approval, daemon=True)
                thread.start()
                deadline = time.monotonic() + 5
                while "CONTROL_URL=" not in output.getvalue():
                    if time.monotonic() >= deadline:
                        self.fail("Approval URL was not shown")
                    time.sleep(0.01)

                console_line = next(
                    line
                    for line in output.getvalue().splitlines()
                    if line.startswith("CONTROL_URL=")
                )
                base_url = console_line.split()[0].removeprefix("CONTROL_URL=")
                approval_url = f"{base_url}/apply?token={token}"
                request = urllib.request.Request(approval_url, data=b"", method="POST")
                with urllib.request.urlopen(request, timeout=2) as response:
                    self.assertEqual(response.status, 200)
                thread.join(timeout=5)

            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(result["command"], "apply")
            self.assertIn(base_url, output.getvalue())
            self.assertIn(token, output.getvalue())
            persisted = (
                status_path.read_text(encoding="utf-8") if status_path.exists() else ""
            )
            self.assertNotIn(base_url, persisted)
            self.assertNotIn(token, persisted)

            with self.assertRaises(urllib.error.URLError):
                urllib.request.urlopen(request, timeout=1)

    def test_parallel_apply_requests_consume_bearer_exactly_once(self) -> None:
        token = "fake-racing-approval-token"
        output = io.StringIO()
        result: dict[str, str] = {}
        errors: list[BaseException] = []
        attempts: list[tuple[str, int | None]] = []
        attempts_lock = threading.Lock()
        request_count = 8
        request_barrier = threading.Barrier(request_count + 1)
        server_class = self.coordinator.ThreadingHTTPServer

        class DelayedShutdownServer(server_class):
            def shutdown(self) -> None:
                time.sleep(0.2)
                super().shutdown()

        def await_approval() -> None:
            try:
                result["command"] = self.coordinator.await_control({"apply", "cancel"})
            except BaseException as error:  # pragma: no cover - surfaced below
                errors.append(error)

        with (
            mock.patch.object(
                self.coordinator.secrets,
                "token_urlsafe",
                return_value=token,
            ),
            mock.patch.object(
                self.coordinator,
                "ThreadingHTTPServer",
                DelayedShutdownServer,
            ),
            contextlib.redirect_stdout(output),
        ):
            approval_thread = threading.Thread(target=await_approval, daemon=True)
            approval_thread.start()
            deadline = time.monotonic() + 5
            while "CONTROL_URL=" not in output.getvalue():
                if time.monotonic() >= deadline:
                    self.fail("Approval URL was not shown")
                time.sleep(0.01)

            console_line = next(
                line
                for line in output.getvalue().splitlines()
                if line.startswith("CONTROL_URL=")
            )
            base_url = console_line.split()[0].removeprefix("CONTROL_URL=")

            def submit(command: str) -> None:
                request_barrier.wait()
                request = urllib.request.Request(
                    f"{base_url}/{command}?token={token}",
                    data=b"",
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(request, timeout=2) as response:
                        status: int | None = response.status
                except urllib.error.HTTPError as error:
                    status = error.code
                except OSError:
                    status = None
                with attempts_lock:
                    attempts.append((command, status))

            request_threads = [
                threading.Thread(
                    target=submit,
                    args=("apply" if index % 2 == 0 else "cancel",),
                    daemon=True,
                )
                for index in range(request_count)
            ]
            for request_thread in request_threads:
                request_thread.start()
            request_barrier.wait()
            for request_thread in request_threads:
                request_thread.join(timeout=5)
            approval_thread.join(timeout=5)

        self.assertTrue(all(not thread.is_alive() for thread in request_threads))
        self.assertFalse(approval_thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(attempts), request_count)
        successful_commands = [command for command, status in attempts if status == 200]
        self.assertEqual(len(successful_commands), 1)
        self.assertEqual(result["command"], successful_commands[0])


if __name__ == "__main__":
    unittest.main()
