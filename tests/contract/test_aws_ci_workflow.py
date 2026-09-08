"""Contract checks for the AWS migration's CI-only artifact boundary."""

from __future__ import annotations

import unittest
from pathlib import Path

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "crawler_deploy.yml"
)


class AwsCiWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_workflow_runs_tests_and_builds_without_publishing(self):
        self.assertIn("name: Crawler AWS Artifact CI", self.workflow)
        self.assertIn("pull_request:", self.workflow)
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertIn("python -m unittest discover -v", self.workflow)
        self.assertIn("python -m compileall -q", self.workflow)
        self.assertIn("docker/build-push-action@v7", self.workflow)
        self.assertIn("push: false", self.workflow)
        self.assertNotIn("push: true", self.workflow)

    def test_workflow_contains_no_gcp_deploy_or_registry_credentials(self):
        forbidden_fragments = (
            "appleboy/ssh-action",
            "docker/login-action",
            "ghcr.io",
            "packages: write",
            "HOST_IP",
            "SSH_USER",
            "SSH_KEY",
            "DB_PASSWORD",
            "UPSTAGE_AI_API_KEY",
        )

        for fragment in forbidden_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, self.workflow)

    def test_workflow_has_no_aws_runtime_or_infrastructure_action(self):
        self.assertNotIn("aws-actions/", self.workflow)
        self.assertNotIn("terraform", self.workflow.lower())
        self.assertIn("permissions:\n  contents: read", self.workflow)


if __name__ == "__main__":
    unittest.main()
