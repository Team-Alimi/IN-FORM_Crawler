from __future__ import annotations

import atexit
import base64
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REGION = "ap-northeast-2"
ROLE_ARN = "arn:aws:iam::869190334503:role/inform-crawler-terraform-dev"
EXPECTED_ACCOUNT = "869190334503"
BACKEND_BUCKET = "inform-crawler-tfstate-869190334503-ap-northeast-2-an"
BACKEND_KEY = "inform-crawler/dev/terraform.tfstate"
TERRAFORM_IMAGE = "hashicorp/terraform:1.16.1"
REPOSITORY_ROOT = Path(__file__).resolve().parent
STATUS_PATH = REPOSITORY_ROOT / ".codex-dev-plan-status.log"
VOLUME_NAME = f"codex-inform-crawler-dev-plan-{secrets.token_hex(8)}"
ALLOWED_UPDATE_ADDRESSES = {
    "module.spot.aws_ssm_document.worker",
    "module.spot.aws_launch_template.worker",
    "module.scheduler.aws_iam_role_policy.orchestration",
    "module.scheduler.aws_sfn_state_machine.crawler",
    "module.scheduler.aws_scheduler_schedule.daily",
}
WORKER_DOCUMENT_ADDRESS = "module.spot.aws_ssm_document.worker"
SCHEDULER_START_DATA_ADDRESS = (
    "module.scheduler.data.aws_iam_policy_document.scheduler_start"
)
SCHEDULER_START_POLICY_ADDRESS = "module.scheduler.aws_iam_role_policy.scheduler_start"
FULL_ROLLOUT_UPDATE_ADDRESSES = ALLOWED_UPDATE_ADDRESSES | {
    SCHEDULER_START_POLICY_ADDRESS
}

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
AWS_KEYS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")
ROLE_CREDENTIAL_EXPIRATION_KEY = "_CODEX_ROLE_CREDENTIAL_EXPIRATION_EPOCH"
HARNESS_PARENT_CLEANUP_BUFFER_SECONDS = 300
HARNESS_FAILURE_STAGES = {
    "DevInfrastructure",
    "DevIdentity",
    "DevNaming",
    "DevDbGuard",
    "DevStateBucket",
    "DevLockTable",
    "DevScheduler",
    "DevStateMachine",
    "CredentialSafetyStop",
    "LiveLeaseContract",
    "LeasePrecondition",
    "ActiveLeaseRejection",
    "ExpiredLeaseTakeover",
    "HeartbeatExtension",
}
_volume_created = False


def emit(message: str) -> None:
    print(message, flush=True)
    with STATUS_PATH.open("a", encoding="utf-8") as status_file:
        status_file.write(message + "\n")


def safe_environment(credentials: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for key in (*AWS_KEYS, "AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        env.pop(key, None)
    env.update(
        {
            "AWS_DEFAULT_REGION": REGION,
            "AWS_REGION": REGION,
            "AWS_PAGER": "",
            "AWS_CLI_AUTO_PROMPT": "off",
            "AWS_EC2_METADATA_DISABLED": "true",
        }
    )
    if credentials:
        for key in AWS_KEYS:
            value = credentials.get(key)
            if value:
                env[key] = value
    return env


def run_quiet(
    arguments: list[str],
    *,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )


def classify_failure(output: str) -> str:
    checks = (
        ("EXPIRED_CREDENTIALS", r"ExpiredToken|RequestExpired|expired"),
        ("AUTHORIZATION_ERROR", r"AccessDenied|Unauthorized|not authorized"),
        ("STATE_LOCKED", r"state lock|Error acquiring the state lock"),
        ("NETWORK_ERROR", r"timeout|timed out|connection|TLS|DNS|resolve host"),
        (
            "INVALID_CONFIGURATION",
            r"InvalidParameter|Invalid value|Unsupported|Missing required",
        ),
    )
    for category, pattern in checks:
        if re.search(pattern, output, re.IGNORECASE):
            return category
    return "UNCLASSIFIED_ERROR"


def classify_harness_failure(output: str) -> str:
    category = classify_failure(output)
    if category != "UNCLASSIFIED_ERROR":
        return category
    checks = (
        (
            "CREDENTIAL_SAFETY_DEADLINE",
            r"DevHarnessCredentialDeadline|before temporary role credentials expire",
        ),
        ("LEASE_PRECONDITION_REJECTED", r"ConditionalCheckFailedException"),
        (
            "LIVE_LEASE_CONTRACT_MISMATCH",
            r"Live worker document is missing the lease contract fragment|"
            r"State machine is missing 'SendWorkerCommand'",
        ),
        (
            "LIVE_LEASE_CONTEXT_INVALID",
            r"ExecutionInputJson (?:is required to verify the live lease path|"
            r"does not identify the worker document)",
        ),
        (
            "POWERSHELL_RUNTIME_ERROR",
            r"A parameter cannot be found that matches parameter name|ParserError",
        ),
    )
    for harness_category, pattern in checks:
        if re.search(pattern, output, re.IGNORECASE):
            return harness_category
    if re.search(
        r"expected '.*' but got '.*'|Controlled overlap did not produce",
        output,
        re.IGNORECASE,
    ):
        return "HARNESS_ASSERTION_FAILED"
    if "AWS CLI command failed without persisted credentials" in output:
        return "AWS_CLI_COMMAND_FAILED"
    return "HARNESS_PROCESS_FAILED"


def harness_failure_stage(output: str) -> str:
    matches = re.findall(
        r"(?m)^HARNESS_STAGE name=([A-Za-z][A-Za-z0-9]*)\s*$",
        output,
    )
    for candidate in reversed(matches):
        if candidate in HARNESS_FAILURE_STAGES:
            return candidate
    return "UNKNOWN"


def b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def aws_json(
    arguments: list[str], credentials: dict[str, str], *, timeout: int = 180
) -> object:
    aws = shutil.which("aws")
    if not aws:
        raise RuntimeError("AWS_CLI_NOT_FOUND")
    result = run_quiet(
        [aws, *arguments, "--region", REGION, "--output", "json", "--no-cli-pager"],
        env=safe_environment(credentials),
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(classify_failure(result.stderr + result.stdout))
    return json.loads(result.stdout)


def aws_s3_object_text(
    bucket: str,
    key: str,
    credentials: dict[str, str],
) -> tuple[str | None, str]:
    aws = shutil.which("aws")
    if not aws:
        return None, "AWS_CLI_NOT_FOUND"
    with tempfile.TemporaryDirectory(prefix="inform-crawler-diagnostic-") as directory:
        destination = Path(directory) / "object"
        result = run_quiet(
            [
                aws,
                "s3api",
                "get-object",
                "--bucket",
                bucket,
                "--key",
                key,
                str(destination),
                "--region",
                REGION,
                "--output",
                "json",
                "--no-cli-pager",
            ],
            env=safe_environment(credentials),
            timeout=180,
        )
        if result.returncode != 0:
            return None, classify_failure(result.stderr + result.stdout)
        return destination.read_text(encoding="utf-8", errors="replace"), "NONE"


def find_failure_artifact_keys(
    bucket: str,
    run_id: str,
    credentials: dict[str, str],
) -> dict[str, str]:
    response = aws_json(
        [
            "s3api",
            "list-objects-v2",
            "--bucket",
            bucket,
            "--query",
            f"Contents[?contains(Key, 'failures/{run_id}/')].Key",
        ],
        credentials,
    )
    keys = response if isinstance(response, list) else []
    result: dict[str, str] = {}
    for value in keys:
        key = str(value)
        if key.endswith("/metadata.json"):
            result["metadata"] = key
        elif key.endswith("/logs/worker.log"):
            result["worker_log"] = key
    return result


def summarize_failure_queues(
    bucket: str,
    run_id: str,
    credentials: dict[str, str],
) -> str:
    response = aws_json(
        [
            "s3api",
            "list-objects-v2",
            "--bucket",
            bucket,
            "--query",
            f"Contents[?contains(Key, 'failures/{run_id}/queue/')].Key",
        ],
        credentials,
    )
    keys = [
        str(value)
        for value in (response if isinstance(response, list) else [])
        if str(value).endswith(".json")
    ]
    file_count = 0
    record_count = 0
    validation_errors: list[str] = []
    from common.db_loader import _resolve_similarity, _validate_record

    class ValidationOnlyCursor:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            return

        def fetchone(self) -> None:
            return None

    cursor = ValidationOnlyCursor()
    for key in keys:
        raw_text, category = aws_s3_object_text(bucket, key, credentials)
        filename = key.replace("\\", "/").rsplit("/", 1)[-1]
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", filename):
            filename = "REDACTED.json"
        if raw_text is None:
            validation_errors.append(f"{filename}:READ_{category}")
            continue
        file_count += 1
        try:
            records = json.loads(raw_text)
        except json.JSONDecodeError:
            validation_errors.append(f"{filename}:INVALID_JSON")
            continue
        if not isinstance(records, list):
            validation_errors.append(f"{filename}:QUEUE_ROOT_NOT_LIST")
            continue
        record_count += len(records)
        for index, record in enumerate(records):
            try:
                validated = _validate_record(record)
                try:
                    _resolve_similarity(cursor, validated["similarity"])
                except LookupError:
                    pass
            except ValueError as error:
                message = str(error)
                fixed_reasons = {
                    "attachments must be a list": "ATTACHMENTS_NOT_LIST",
                    "each attachment must be an object": "ATTACHMENT_NOT_OBJECT",
                    "crawler attachments must be EXTERNAL file_url objects": "ATTACHMENT_NOT_EXTERNAL_URL",
                    "attachment file_url is required": "ATTACHMENT_URL_MISSING",
                    "crawler record must be an object": "CRAWLER_RECORD_NOT_OBJECT",
                    "queue record must be an object": "QUEUE_RECORD_NOT_OBJECT",
                    "crawler writer accepts SCHOOL records only": "NON_SCHOOL_RECORD",
                    "similarity must contain score and candidate source identity": "SIMILARITY_IDENTITY_MISSING",
                    "similarity score must be numeric": "SIMILARITY_SCORE_NOT_NUMERIC",
                    "similarity score must be between 0 and 100": "SIMILARITY_SCORE_OUT_OF_RANGE",
                }
                reason = fixed_reasons.get(message, "UNCLASSIFIED_VALUE_ERROR")
                field_error = re.fullmatch(
                    r"(source_type|vendor_initial|external_key|source_url|title|content|"
                    r"start_date|due_date|published_at|category_code) "
                    r"(is required|must be an ISO date or timestamp string)",
                    message,
                )
                if field_error:
                    suffix = (
                        "REQUIRED"
                        if field_error.group(2) == "is required"
                        else "INVALID_DATE_TYPE"
                    )
                    reason = f"{field_error.group(1).upper()}_{suffix}"
                validation_errors.append(f"{filename}:{index}:{reason}")
            except Exception as error:
                validation_errors.append(
                    f"{filename}:{index}:UNEXPECTED_{type(error).__name__.upper()}"
                )
    return (
        f"files={file_count} records={record_count} "
        f"validation_errors={len(validation_errors)} "
        f"details={','.join(validation_errors[:8]) or 'none'}"
    )


def assume_role(access_key: str, secret_key: str, session_token: str) -> dict[str, str]:
    source = {
        "AWS_ACCESS_KEY_ID": access_key,
        "AWS_SECRET_ACCESS_KEY": secret_key,
    }
    if session_token:
        source["AWS_SESSION_TOKEN"] = session_token
    response = aws_json(
        [
            "sts",
            "assume-role",
            "--role-arn",
            ROLE_ARN,
            "--role-session-name",
            f"codex-dev-plan-{secrets.token_hex(4)}",
            "--duration-seconds",
            "3600",
        ],
        source,
    )
    if not isinstance(response, dict) or not isinstance(
        response.get("Credentials"), dict
    ):
        raise RuntimeError("ASSUME_ROLE_RESPONSE_INVALID")
    data = response["Credentials"]
    try:
        expiration_epoch = int(
            datetime.fromisoformat(
                str(data["Expiration"]).replace("Z", "+00:00")
            ).timestamp()
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("ASSUME_ROLE_EXPIRATION_INVALID") from error
    if expiration_epoch <= int(time.time()):
        raise RuntimeError("ASSUME_ROLE_EXPIRATION_INVALID")
    credentials = {
        "AWS_ACCESS_KEY_ID": str(data["AccessKeyId"]),
        "AWS_SECRET_ACCESS_KEY": str(data["SecretAccessKey"]),
        "AWS_SESSION_TOKEN": str(data["SessionToken"]),
        ROLE_CREDENTIAL_EXPIRATION_KEY: str(expiration_epoch),
    }
    identity = aws_json(["sts", "get-caller-identity"], credentials)
    if not isinstance(identity, dict):
        raise RuntimeError("CALLER_IDENTITY_INVALID")
    arn = str(identity.get("Arn", ""))
    if (
        identity.get("Account") != EXPECTED_ACCOUNT
        or "/inform-crawler-terraform-dev/" not in arn
    ):
        raise RuntimeError("UNEXPECTED_CALLER_IDENTITY")
    return credentials


def publish_image(credentials: dict[str, str]) -> tuple[str, str, str]:
    emit("ECR_STAGE name=caller-identity")
    identity = aws_json(["sts", "get-caller-identity"], credentials)
    if not isinstance(identity, dict) or identity.get("Account") != EXPECTED_ACCOUNT:
        raise RuntimeError("UNEXPECTED_PUBLISHER_IDENTITY")
    emit("ECR_STAGE name=describe-repository")
    repositories = aws_json(
        ["ecr", "describe-repositories", "--repository-names", "inform-crawler-dev"],
        credentials,
    )
    repository_list = (
        repositories.get("repositories", []) if isinstance(repositories, dict) else []
    )
    if len(repository_list) != 1 or not isinstance(repository_list[0], dict):
        raise RuntimeError("ECR_REPOSITORY_LOOKUP_FAILED")
    repository = repository_list[0]
    repository_uri = str(repository.get("repositoryUri", ""))
    repository_arn = str(repository.get("repositoryArn", ""))
    if not repository_uri or not repository_arn:
        raise RuntimeError("ECR_REPOSITORY_IDENTITY_MISSING")

    git = shutil.which("git")
    docker = shutil.which("docker")
    aws = shutil.which("aws")
    if not git or not docker or not aws:
        raise RuntimeError("RELEASE_TOOL_NOT_FOUND")
    revision = run_quiet([git, "rev-parse", "HEAD"], timeout=30)
    if revision.returncode != 0:
        raise RuntimeError("GIT_REVISION_LOOKUP_FAILED")
    git_sha = revision.stdout.strip()
    image_tag = git_sha[:12]
    local_image = f"inform-crawler:{image_tag}"
    remote_image = f"{repository_uri}:{image_tag}"
    inspect = run_quiet([docker, "image", "inspect", local_image], timeout=60)
    if inspect.returncode != 0:
        raise RuntimeError("LOCAL_RELEASE_IMAGE_MISSING")

    emit("ECR_STAGE name=get-login-password")
    password = run_quiet(
        [aws, "ecr", "get-login-password", "--region", REGION],
        env=safe_environment(credentials),
        timeout=180,
    )
    if password.returncode != 0:
        raise RuntimeError(classify_failure(password.stderr + password.stdout))
    registry = repository_uri.split("/", 1)[0]
    emit("ECR_STAGE name=docker-login")
    login = run_quiet(
        [docker, "login", "--username", "AWS", "--password-stdin", registry],
        input_text=password.stdout,
        timeout=180,
    )
    password = None
    if login.returncode != 0:
        raise RuntimeError(classify_failure(login.stderr + login.stdout))
    try:
        emit("ECR_STAGE name=tag-local-image")
        tagged = run_quiet([docker, "tag", local_image, remote_image], timeout=60)
        if tagged.returncode != 0:
            raise RuntimeError("DOCKER_TAG_FAILED")
        emit("ECR_STAGE name=push-image")
        pushed = run_quiet([docker, "push", remote_image], timeout=1800)
        if pushed.returncode != 0:
            raise RuntimeError(classify_failure(pushed.stderr + pushed.stdout))
    finally:
        run_quiet([docker, "logout", registry], timeout=60)

    emit("ECR_STAGE name=resolve-digest")
    images = aws_json(
        [
            "ecr",
            "describe-images",
            "--repository-name",
            "inform-crawler-dev",
            "--image-ids",
            f"imageTag={image_tag}",
        ],
        credentials,
    )
    details = images.get("imageDetails", []) if isinstance(images, dict) else []
    digest = str(details[0].get("imageDigest", "")) if details else ""
    if not digest.startswith("sha256:"):
        raise RuntimeError("ECR_IMAGE_DIGEST_MISSING")
    emit("ECR_IMAGE_PUBLISHED immutable=true")
    return f"{repository_uri}@{digest}", repository_arn, git_sha


def resolve_existing_image(credentials: dict[str, str]) -> tuple[str, str, str]:
    identity = aws_json(["sts", "get-caller-identity"], credentials)
    if not isinstance(identity, dict) or identity.get("Account") != EXPECTED_ACCOUNT:
        raise RuntimeError("UNEXPECTED_PUBLISHER_IDENTITY")
    repositories = aws_json(
        ["ecr", "describe-repositories", "--repository-names", "inform-crawler-dev"],
        credentials,
    )
    repository_list = (
        repositories.get("repositories", []) if isinstance(repositories, dict) else []
    )
    if len(repository_list) != 1 or not isinstance(repository_list[0], dict):
        raise RuntimeError("ECR_REPOSITORY_LOOKUP_FAILED")
    repository = repository_list[0]
    repository_uri = str(repository.get("repositoryUri", ""))
    repository_arn = str(repository.get("repositoryArn", ""))
    if not repository_uri or not repository_arn:
        raise RuntimeError("ECR_REPOSITORY_IDENTITY_MISSING")

    git = shutil.which("git")
    if not git:
        raise RuntimeError("GIT_NOT_FOUND")
    revision = run_quiet([git, "rev-parse", "HEAD"], timeout=30)
    if revision.returncode != 0:
        raise RuntimeError("GIT_REVISION_LOOKUP_FAILED")
    git_sha = revision.stdout.strip()
    image_tag = git_sha[:12]
    images = aws_json(
        [
            "ecr",
            "describe-images",
            "--repository-name",
            "inform-crawler-dev",
            "--image-ids",
            f"imageTag={image_tag}",
        ],
        credentials,
    )
    details = images.get("imageDetails", []) if isinstance(images, dict) else []
    digest = str(details[0].get("imageDigest", "")) if details else ""
    if not digest.startswith("sha256:"):
        raise RuntimeError("ECR_IMAGE_DIGEST_MISSING")
    emit("ECR_IMAGE_RESOLVED immutable=true")
    return f"{repository_uri}@{digest}", repository_arn, git_sha


def pull_remote_state(credentials: dict[str, str]) -> dict[str, object]:
    aws = shutil.which("aws")
    if not aws:
        raise RuntimeError("AWS_CLI_NOT_FOUND")
    result = run_quiet(
        [
            aws,
            "s3",
            "cp",
            f"s3://{BACKEND_BUCKET}/{BACKEND_KEY}",
            "-",
            "--region",
            REGION,
            "--no-progress",
            "--no-cli-pager",
        ],
        env=safe_environment(credentials),
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(classify_failure(result.stderr + result.stdout))
    state = json.loads(result.stdout)
    if not isinstance(state, dict) or not isinstance(state.get("resources"), list):
        raise RuntimeError("REMOTE_STATE_INVALID")
    return state


def resource_attributes(
    state: dict[str, object], module: str, resource_type: str, name: str
) -> dict[str, object] | None:
    for resource in state.get("resources", []):
        if not isinstance(resource, dict):
            continue
        if (
            resource.get("module") == module
            and resource.get("type") == resource_type
            and resource.get("name") == name
        ):
            for instance in resource.get("instances", []):
                if isinstance(instance, dict) and isinstance(
                    instance.get("attributes"), dict
                ):
                    return instance["attributes"]
    return None


def require_attributes(
    state: dict[str, object], module: str, resource_type: str, name: str
) -> dict[str, object]:
    result = resource_attributes(state, module, resource_type, name)
    if result is None:
        raise RuntimeError(f"STATE_RESOURCE_MISSING:{module}.{resource_type}.{name}")
    return result


def parse_shell_constant(content: str, name: str) -> str:
    match = re.search(
        rf"^readonly {re.escape(name)}='([^']*)'\r?$", content, re.MULTILINE
    )
    if not match:
        raise RuntimeError(f"STATE_CONSTANT_MISSING:{name}")
    return match.group(1)


def policy_resource(
    policy_text: str, required_action: str, resource_pattern: str
) -> str:
    policy = json.loads(policy_text)
    for statement in policy.get("Statement", []):
        actions = statement.get("Action", [])
        if isinstance(actions, str):
            actions = [actions]
        if required_action not in actions:
            continue
        resources = statement.get("Resource", [])
        if isinstance(resources, str):
            resources = [resources]
        for resource in resources:
            if re.search(resource_pattern, str(resource)):
                return str(resource)
    raise RuntimeError(f"STATE_POLICY_RESOURCE_MISSING:{required_action}")


def derive_variables(
    state: dict[str, object], credentials: dict[str, str]
) -> dict[str, object]:
    bucket = require_attributes(state, "module.state", "aws_s3_bucket", "state")
    launch_template = require_attributes(
        state, "module.spot", "aws_launch_template", "worker"
    )
    worker_document = require_attributes(
        state, "module.spot", "aws_ssm_document", "worker"
    )
    state_machine = require_attributes(
        state, "module.scheduler", "aws_sfn_state_machine", "crawler"
    )
    ingress = require_attributes(
        state,
        "module.network",
        "aws_vpc_security_group_ingress_rule",
        "postgres_from_crawler",
    )
    runtime_policy = require_attributes(
        state, "module.iam", "aws_iam_role_policy", "runtime"
    )

    definition = json.loads(str(state_machine.get("definition", "")))
    try:
        overrides = definition["States"]["LaunchSpotWorker"]["Parameters"][
            "LaunchTemplateConfigs"
        ][0]["Overrides"]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("STATE_FLEET_OVERRIDES_MISSING") from error
    if not isinstance(overrides, list) or not overrides:
        raise RuntimeError("STATE_FLEET_OVERRIDES_MISSING")
    subnet_ids: list[str] = []
    instance_types: list[str] = []
    for override in overrides:
        if not isinstance(override, dict):
            continue
        subnet_id = str(override.get("SubnetId", ""))
        instance_type = str(override.get("InstanceType", ""))
        if subnet_id and subnet_id not in subnet_ids:
            subnet_ids.append(subnet_id)
        if instance_type and instance_type not in instance_types:
            instance_types.append(instance_type)
    if len(subnet_ids) < 2 or len(instance_types) < 2:
        raise RuntimeError("STATE_FLEET_DIVERSITY_INVALID")

    crawler_group = resource_attributes(
        state, "module.network", "aws_security_group", "crawler"
    )
    crawler_security_group_id: str | None = None
    if crawler_group is not None:
        vpc_id = str(crawler_group.get("vpc_id", ""))
    else:
        crawler_security_group_id = str(ingress.get("referenced_security_group_id", ""))
        groups = aws_json(
            [
                "ec2",
                "describe-security-groups",
                "--group-ids",
                crawler_security_group_id,
            ],
            credentials,
        )
        group_list = (
            groups.get("SecurityGroups", []) if isinstance(groups, dict) else []
        )
        if not group_list:
            raise RuntimeError("CRAWLER_SECURITY_GROUP_LOOKUP_FAILED")
        vpc_id = str(group_list[0].get("VpcId", ""))
    if not vpc_id:
        raise RuntimeError("STATE_VPC_ID_MISSING")

    document = json.loads(str(worker_document.get("content", "")))
    steps = document.get("mainSteps", []) if isinstance(document, dict) else []
    if not steps or not isinstance(steps[0], dict):
        raise RuntimeError("STATE_WORKER_DOCUMENT_INVALID")
    inputs = steps[0].get("inputs", {})
    commands = inputs.get("runCommand", []) if isinstance(inputs, dict) else []
    if not isinstance(commands, list) or not commands:
        raise RuntimeError("STATE_WORKER_COMMAND_MISSING")
    content = "\n".join(str(command) for command in commands)
    policy_text = str(runtime_policy.get("policy", ""))
    raw_tags = bucket.get("tags") if isinstance(bucket.get("tags"), dict) else {}
    tags = {
        str(key): str(value)
        for key, value in raw_tags.items()
        if key not in {"Application", "Environment", "ManagedBy"}
    }
    variables: dict[str, object] = {
        "region": REGION,
        "vpc_id": vpc_id,
        "subnet_ids": subnet_ids,
        "crawler_security_group_id": crawler_security_group_id,
        "main_db_security_group_id": str(ingress.get("security_group_id", "")),
        "candidate_instance_types": instance_types,
        "state_bucket_name": str(bucket.get("bucket", "")),
        "state_prefix": parse_shell_constant(content, "STATE_PREFIX"),
        "parameter_store_namespace": parse_shell_constant(
            content, "PARAMETER_NAMESPACE"
        ),
        "database_secret_arn": parse_shell_constant(content, "DATABASE_SECRET_ARN"),
        "crawler_ecr_repository_arn": policy_resource(
            policy_text, "ecr:BatchGetImage", r":repository/"
        ),
        "ami_id": str(launch_template.get("image_id", "")),
        "crawler_image_ref": parse_shell_constant(content, "CRAWLER_IMAGE_REF"),
        "crawler_git_sha": parse_shell_constant(content, "CRAWLER_GIT_SHA"),
        "schedule_enabled": False,
        "tags": tags,
    }
    empty_allowed = {"state_prefix"}
    missing = [
        key
        for key, value in variables.items()
        if value == "" and key not in empty_allowed
    ]
    if missing:
        raise RuntimeError("STATE_INPUTS_MISSING:" + ",".join(sorted(missing)))
    return variables


PLAN_SCRIPT = r"""
set -eu
IFS= read -r CODEX_AK
IFS= read -r CODEX_SK
IFS= read -r CODEX_ST
IFS= read -r CODEX_VARS
export AWS_ACCESS_KEY_ID="$(printf '%s' "$CODEX_AK" | base64 -d)"
export AWS_SECRET_ACCESS_KEY="$(printf '%s' "$CODEX_SK" | base64 -d)"
export AWS_SESSION_TOKEN="$(printf '%s' "$CODEX_ST" | base64 -d)"
unset CODEX_AK CODEX_SK CODEX_ST
export AWS_DEFAULT_REGION='ap-northeast-2'
export AWS_REGION='ap-northeast-2'
export AWS_EC2_METADATA_DISABLED='true'
export TF_IN_AUTOMATION='true'
cp -a /source/infra/aws/crawler/. /work/
rm -rf /work/environments/dev/.terraform /work/environments/prod/.terraform
printf '%s' "$CODEX_VARS" | base64 -d > /work/environments/dev/terraform.auto.tfvars.json
unset CODEX_VARS
terraform -chdir=/work/environments/dev init -input=false -no-color -lockfile=readonly -reconfigure \
  -backend-config='bucket=inform-crawler-tfstate-869190334503-ap-northeast-2-an' \
  -backend-config='key=inform-crawler/dev/terraform.tfstate' \
  -backend-config='region=ap-northeast-2' >/tmp/init.log 2>&1 || {
    printf '__CODEX_ERROR__:INIT\n'
    tail -n 80 /tmp/init.log
    exit 10
  }
set +e
terraform -chdir=/work/environments/dev plan -input=false -no-color -lock=false \
  -detailed-exitcode -out=/work/dev.tfplan >/tmp/plan.log 2>&1
CODEX_RC=$?
set -e
if [ "$CODEX_RC" -ne 0 ] && [ "$CODEX_RC" -ne 2 ]; then
  printf '__CODEX_ERROR__:PLAN\n'
  tail -n 100 /tmp/plan.log
  exit 11
fi
printf '__CODEX_PLAN_JSON__\n'
terraform -chdir=/work/environments/dev show -json /work/dev.tfplan
"""


APPLY_SCRIPT = r"""
set -eu
IFS= read -r CODEX_AK
IFS= read -r CODEX_SK
IFS= read -r CODEX_ST
export AWS_ACCESS_KEY_ID="$(printf '%s' "$CODEX_AK" | base64 -d)"
export AWS_SECRET_ACCESS_KEY="$(printf '%s' "$CODEX_SK" | base64 -d)"
export AWS_SESSION_TOKEN="$(printf '%s' "$CODEX_ST" | base64 -d)"
unset CODEX_AK CODEX_SK CODEX_ST
export AWS_DEFAULT_REGION='ap-northeast-2'
export AWS_REGION='ap-northeast-2'
export AWS_EC2_METADATA_DISABLED='true'
export TF_IN_AUTOMATION='true'
terraform -chdir=/work/environments/dev apply -input=false -no-color -lock-timeout=300s \
  /work/dev.tfplan >/tmp/apply.log 2>&1 || {
    printf '__CODEX_ERROR__:APPLY\n'
    tail -n 100 /tmp/apply.log
    exit 20
  }
set +e
terraform -chdir=/work/environments/dev plan -input=false -no-color -lock=false \
  -detailed-exitcode -out=/work/convergence.tfplan >/tmp/convergence.log 2>&1
CODEX_RC=$?
set -e
if [ "$CODEX_RC" -eq 0 ]; then
  printf '__CODEX_APPLY_CONVERGED__\n'
  exit 0
fi
if [ "$CODEX_RC" -eq 2 ]; then
  printf '__CODEX_CONVERGENCE_JSON__\n'
  terraform -chdir=/work/environments/dev show -json /work/convergence.tfplan
  exit 21
fi
printf '__CODEX_ERROR__:CONVERGENCE\n'
tail -n 100 /tmp/convergence.log
exit 22
"""


def docker_payload(credentials: dict[str, str], extra: str | None = None) -> str:
    lines = [b64(credentials[key]) for key in AWS_KEYS]
    if extra is not None:
        lines.append(b64(extra))
    return "\n".join(lines) + "\n"


def docker_run(
    script: str, payload: str, timeout: int = 1200
) -> subprocess.CompletedProcess[str]:
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("DOCKER_NOT_FOUND")
    return run_quiet(
        [
            docker,
            "run",
            "--rm",
            "-i",
            "--mount",
            f"type=volume,source={VOLUME_NAME},target=/work",
            "--mount",
            f"type=bind,source={REPOSITORY_ROOT},target=/source,readonly",
            "--entrypoint",
            "/bin/sh",
            TERRAFORM_IMAGE,
            "-c",
            script,
        ],
        input_text=payload,
        timeout=timeout,
    )


def create_volume() -> None:
    global _volume_created
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("DOCKER_NOT_FOUND")
    result = run_quiet([docker, "volume", "create", VOLUME_NAME], timeout=60)
    if result.returncode != 0 or result.stdout.strip() != VOLUME_NAME:
        raise RuntimeError("PLAN_VOLUME_CREATE_FAILED")
    _volume_created = True


def cleanup_volume() -> None:
    global _volume_created
    if not _volume_created:
        return
    if not re.fullmatch(r"codex-inform-crawler-dev-plan-[0-9a-f]{16}", VOLUME_NAME):
        raise RuntimeError("PLAN_VOLUME_NAME_INVALID")
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("DOCKER_NOT_FOUND")
    result = run_quiet([docker, "volume", "rm", "-f", VOLUME_NAME], timeout=60)
    if result.returncode != 0:
        raise RuntimeError("PLAN_VOLUME_REMOVE_FAILED")
    _volume_created = False


def cleanup_volume_at_exit() -> None:
    try:
        cleanup_volume()
    except Exception as error:
        category = str(error).split(":", 1)[0] or type(error).__name__
        print(
            f"PLAN_VOLUME_CLEANUP_AT_EXIT_FAILED category={category}", file=sys.stderr
        )


def summarize_plan(
    plan: dict[str, object],
) -> tuple[dict[str, int], list[tuple[str, str]], str]:
    summary = {"create": 0, "update": 0, "delete": 0, "replace": 0}
    changes: list[tuple[str, str]] = []
    schedule_state = ""
    for change in plan.get("resource_changes", []):
        if not isinstance(change, dict) or not isinstance(change.get("change"), dict):
            continue
        address = str(change.get("address", ""))
        change_data = change["change"]
        actions = [str(action) for action in change_data.get("actions", [])]
        if address == "module.scheduler.aws_scheduler_schedule.daily":
            after = change_data.get("after")
            if isinstance(after, dict):
                schedule_state = str(after.get("state", ""))
        if actions in (["no-op"], ["read"]):
            continue
        action_text = ",".join(actions)
        changes.append((address, action_text))
        if "create" in actions and "delete" in actions:
            summary["replace"] += 1
        elif actions == ["create"]:
            summary["create"] += 1
        elif actions == ["update"]:
            summary["update"] += 1
        elif actions == ["delete"]:
            summary["delete"] += 1
    return summary, changes, schedule_state


def truthy_unknown_paths(value: object, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if value is True:
        paths.add(prefix)
    elif isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.update(truthy_unknown_paths(child, child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_prefix = f"{prefix}[{index}]"
            paths.update(truthy_unknown_paths(child, child_prefix))
    return paths


def scheduler_start_is_safe_dependency_refresh(plan: dict[str, object]) -> bool:
    resource_changes = [
        change
        for change in plan.get("resource_changes", [])
        if isinstance(change, dict)
    ]
    by_address = {str(change.get("address", "")): change for change in resource_changes}
    data_change = by_address.get(SCHEDULER_START_DATA_ADDRESS)
    policy_change = by_address.get(SCHEDULER_START_POLICY_ADDRESS)
    state_machine_change = by_address.get(
        "module.scheduler.aws_sfn_state_machine.crawler"
    )
    if not data_change or not policy_change or not state_machine_change:
        return False
    if data_change.get("change", {}).get("actions") != ["read"]:
        return False
    if state_machine_change.get("change", {}).get("actions") != ["update"]:
        return False
    policy_delta = policy_change.get("change", {})
    if policy_delta.get("actions") != ["update"]:
        return False
    before = policy_delta.get("before")
    after = policy_delta.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    known_differences = {
        key
        for key in set(before) | set(after)
        if key != "policy" and before.get(key) != after.get(key)
    }
    if known_differences:
        return False
    unknown_paths = truthy_unknown_paths(policy_delta.get("after_unknown", {}))
    if unknown_paths != {"policy"}:
        return False
    try:
        current_policy = json.loads(str(before.get("policy", "")))
    except json.JSONDecodeError:
        return False
    statements = current_policy.get("Statement", [])
    if isinstance(statements, dict):
        statements = [statements]
    if len(statements) != 1 or not isinstance(statements[0], dict):
        return False
    statement = statements[0]
    action = statement.get("Action")
    if isinstance(action, list):
        action = action[0] if len(action) == 1 else ""
    resource = statement.get("Resource")
    if isinstance(resource, list):
        resource = resource[0] if len(resource) == 1 else ""
    return (
        statement.get("Sid") == "StartOnlyCrawlerOrchestration"
        and statement.get("Effect") == "Allow"
        and action == "states:StartExecution"
        and bool(
            re.fullmatch(
                r"arn:aws[a-zA-Z-]*:states:[^:]+:\d{12}:stateMachine:inform-crawler-orchestration-dev",
                str(resource),
            )
        )
    )


def execute_plan(
    credentials: dict[str, str],
    variable_overrides: dict[str, object] | None = None,
    expected_update_addresses: set[str] | None = None,
) -> bool:
    emit("DEV_PLAN_STAGE=REMOTE_STATE_READ")
    state = pull_remote_state(credentials)
    variables = derive_variables(state, credentials)
    if variable_overrides:
        variables.update(variable_overrides)
    del state
    emit("DEV_PLAN_STAGE=INPUTS_DERIVED")
    create_volume()
    result = docker_run(PLAN_SCRIPT, docker_payload(credentials, json.dumps(variables)))
    del variables
    marker = "__CODEX_PLAN_JSON__\n"
    combined = result.stdout + result.stderr
    if result.returncode not in (0, 2) or marker not in result.stdout:
        emit(f"DEV_PLAN_FAILED category={classify_failure(combined)}")
        return False
    plan = json.loads(result.stdout.split(marker, 1)[1])
    summary, changes, schedule_state = summarize_plan(plan)
    scheduler_dependency_refresh = scheduler_start_is_safe_dependency_refresh(plan)
    del plan
    for address, actions in changes:
        emit(f"DEV_PLAN_ACTION address={address} actions={actions}")
    emit(
        "DEV_PLAN_SUMMARY "
        + " ".join(f"{key}={value}" for key, value in summary.items())
        + f" schedule_state={schedule_state or 'UNKNOWN'}"
    )
    changed_addresses = {address for address, _ in changes}
    permitted_addresses = set(ALLOWED_UPDATE_ADDRESSES)
    if scheduler_dependency_refresh:
        permitted_addresses.add(SCHEDULER_START_POLICY_ADDRESS)
        emit("DEV_PLAN_DETAIL scheduler_start=safe_dependency_refresh")
    expected_update_shape = (
        "module.scheduler.aws_sfn_state_machine.crawler" in changed_addresses
        or changed_addresses == {WORKER_DOCUMENT_ADDRESS}
    )
    accepted = (
        summary["create"] == 0
        and summary["delete"] == 0
        and summary["replace"] == 0
        and summary["update"] == len(changes)
        and bool(changes)
        and changed_addresses.issubset(permitted_addresses)
        and (
            expected_update_addresses is None
            or changed_addresses == expected_update_addresses
        )
        and expected_update_shape
        and schedule_state == "DISABLED"
    )
    emit(f"DEV_PLAN_SAFETY={'ACCEPTED' if accepted else 'REJECTED'}")
    return accepted


def execute_apply(credentials: dict[str, str]) -> bool:
    result = docker_run(APPLY_SCRIPT, docker_payload(credentials), timeout=1800)
    combined = result.stdout + result.stderr
    if result.returncode == 0 and "__CODEX_APPLY_CONVERGED__" in result.stdout:
        emit("DEV_APPLY_COMPLETE converged=true schedule_enabled=false")
        return True
    marker = "__CODEX_CONVERGENCE_JSON__\n"
    if marker in result.stdout:
        plan = json.loads(result.stdout.split(marker, 1)[1])
        summary, changes, schedule_state = summarize_plan(plan)
        emit(
            "DEV_APPLY_DRIFT "
            + " ".join(f"{key}={value}" for key, value in summary.items())
            + f" schedule_state={schedule_state or 'UNKNOWN'}"
        )
        for address, actions in changes:
            emit(f"DEV_APPLY_DRIFT_ACTION address={address} actions={actions}")
        return False
    emit(f"DEV_APPLY_FAILED category={classify_failure(combined)}")
    return False


def derive_harness_context(state: dict[str, object]) -> dict[str, str]:
    bucket = require_attributes(state, "module.state", "aws_s3_bucket", "state")
    lock_table = require_attributes(
        state, "module.state", "aws_dynamodb_table", "runtime_lock"
    )
    schedule = require_attributes(
        state, "module.scheduler", "aws_scheduler_schedule", "daily"
    )
    state_machine = require_attributes(
        state, "module.scheduler", "aws_sfn_state_machine", "crawler"
    )
    worker_document = require_attributes(
        state, "module.spot", "aws_ssm_document", "worker"
    )
    targets = schedule.get("target")
    if not isinstance(targets, list) or not targets or not isinstance(targets[0], dict):
        raise RuntimeError("STATE_SCHEDULE_TARGET_MISSING")
    execution_input = str(targets[0].get("input", ""))
    parsed_input = json.loads(execution_input)
    if not isinstance(parsed_input, dict):
        raise RuntimeError("STATE_EXECUTION_INPUT_INVALID")
    definition = json.loads(str(state_machine.get("definition", "")))
    try:
        overrides = definition["States"]["LaunchSpotWorker"]["Parameters"][
            "LaunchTemplateConfigs"
        ][0]["Overrides"]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("STATE_FLEET_OVERRIDES_MISSING") from error
    if not isinstance(overrides, list) or not overrides:
        raise RuntimeError("STATE_FLEET_OVERRIDES_INVALID")
    document = json.loads(str(worker_document.get("content", "")))
    steps = document.get("mainSteps", []) if isinstance(document, dict) else []
    if not steps or not isinstance(steps[0], dict):
        raise RuntimeError("STATE_WORKER_DOCUMENT_INVALID")
    inputs = steps[0].get("inputs", {})
    commands = inputs.get("runCommand", []) if isinstance(inputs, dict) else []
    if not isinstance(commands, list) or not commands:
        raise RuntimeError("STATE_WORKER_COMMAND_MISSING")
    worker_command = "\n".join(str(command) for command in commands)
    namespace = parse_shell_constant(worker_command, "PARAMETER_NAMESPACE").rstrip("/")
    context = {
        "state_bucket": str(bucket.get("bucket", "")),
        "lock_table": str(lock_table.get("name", "")),
        "schedule_name": str(schedule.get("name", "")),
        "state_machine_arn": str(state_machine.get("arn", "")),
        "guard_parameter": namespace + "/PRODUCTION_DB_ACCESS_ALLOWED",
        "execution_input": execution_input,
    }
    missing = [key for key, value in context.items() if not value]
    if missing:
        raise RuntimeError("HARNESS_CONTEXT_MISSING:" + ",".join(sorted(missing)))
    return context


def list_dev_workers(credentials: dict[str, str]) -> dict[str, str]:
    response = aws_json(
        [
            "ec2",
            "describe-instances",
            "--filters",
            "Name=tag:Application,Values=inform-crawler",
            "Name=tag:Environment,Values=dev",
            "Name=instance-state-name,Values=pending,running,stopping,stopped,shutting-down",
        ],
        credentials,
    )
    workers: dict[str, str] = {}
    reservations = (
        response.get("Reservations", []) if isinstance(response, dict) else []
    )
    for reservation in reservations:
        if not isinstance(reservation, dict):
            continue
        for instance in reservation.get("Instances", []):
            if not isinstance(instance, dict):
                continue
            instance_id = str(instance.get("InstanceId", ""))
            state = instance.get("State", {})
            state_name = str(state.get("Name", "")) if isinstance(state, dict) else ""
            if instance_id:
                workers[instance_id] = state_name
    return workers


def stop_matching_harness_executions(
    credentials: dict[str, str], state_machine_arn: str, harness_run_id: str
) -> int:
    if not re.fullmatch(r"[a-z0-9]{6,32}", harness_run_id):
        raise RuntimeError("HARNESS_RUN_ID_INVALID")
    state_machine_parts = state_machine_arn.split(":", 6)
    if (
        len(state_machine_parts) != 7
        or state_machine_parts[2] != "states"
        or state_machine_parts[5] != "stateMachine"
    ):
        raise RuntimeError("HARNESS_STATE_MACHINE_ARN_INVALID")
    execution_arn_prefix = (
        ":".join(state_machine_parts[:5]) + ":execution:" + state_machine_parts[6] + ":"
    )
    execution_name_prefix = f"harness-{harness_run_id}-"
    response = aws_json(
        [
            "stepfunctions",
            "list-executions",
            "--state-machine-arn",
            state_machine_arn,
            "--status-filter",
            "RUNNING",
            "--max-results",
            "100",
        ],
        credentials,
        timeout=30,
    )
    executions = response.get("executions", []) if isinstance(response, dict) else []
    matching_arns: list[str] = []
    for execution in executions:
        if not isinstance(execution, dict):
            continue
        name = str(execution.get("name", ""))
        execution_arn = str(execution.get("executionArn", ""))
        if name.startswith(execution_name_prefix) and execution_arn.startswith(
            execution_arn_prefix
        ):
            matching_arns.append(execution_arn)
    stopped = 0
    failed = 0
    for execution_arn in matching_arns:
        try:
            aws_json(
                [
                    "stepfunctions",
                    "stop-execution",
                    "--execution-arn",
                    execution_arn,
                    "--error",
                    "DevHarnessParentCleanup",
                    "--cause",
                    "Stopped by the bounded coordinator cleanup path.",
                ],
                credentials,
                timeout=30,
            )
            stopped += 1
        except Exception:
            failed += 1
    if failed:
        raise RuntimeError(f"HARNESS_EXECUTION_STOP_FAILED:{failed}")
    return stopped


def cleanup_new_workers(
    credentials: dict[str, str], baseline_ids: set[str], timeout: int = 900
) -> None:
    current = list_dev_workers(credentials)
    new_workers = {
        instance_id: state
        for instance_id, state in current.items()
        if instance_id not in baseline_ids
    }
    terminable = [
        instance_id
        for instance_id, state in new_workers.items()
        if state in {"pending", "running", "stopping", "stopped"}
    ]
    if terminable:
        aws_json(
            ["ec2", "terminate-instances", "--instance-ids", *terminable], credentials
        )
        emit(f"HARNESS_CLEANUP_REQUESTED count={len(terminable)}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = {
            instance_id: state
            for instance_id, state in list_dev_workers(credentials).items()
            if instance_id not in baseline_ids
        }
        if not remaining:
            emit("HARNESS_CLEANUP_COMPLETE remaining=0")
            return
        emit(f"HARNESS_CLEANUP_WAIT remaining={len(remaining)}")
        time.sleep(30)
    raise RuntimeError("HARNESS_CLEANUP_TIMEOUT")


def run_harness_scenario(
    credentials: dict[str, str], context: dict[str, str], scenario: str
) -> bool:
    pwsh = shutil.which("pwsh")
    if not pwsh:
        raise RuntimeError("POWERSHELL_7_NOT_FOUND")
    try:
        credential_expiration_epoch = int(credentials[ROLE_CREDENTIAL_EXPIRATION_KEY])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("ROLE_CREDENTIAL_EXPIRATION_MISSING") from error
    parent_deadline_epoch = (
        credential_expiration_epoch - HARNESS_PARENT_CLEANUP_BUFFER_SECONDS
    )
    if parent_deadline_epoch <= int(time.time()):
        raise RuntimeError("ROLE_CREDENTIAL_LIFETIME_INSUFFICIENT")
    harness_run_id = secrets.token_hex(8)
    script_path = REPOSITORY_ROOT / "infra/aws/crawler/harness/run-dev.ps1"
    arguments = [
        pwsh,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-ExpectedAccountId",
        EXPECTED_ACCOUNT,
        "-ExpectedRegion",
        REGION,
        "-DevStateBucket",
        context["state_bucket"],
        "-DevLockTable",
        context["lock_table"],
        "-DevSchedulerName",
        context["schedule_name"],
        "-DevStateMachineArn",
        context["state_machine_arn"],
        "-DevDbGuardParameter",
        context["guard_parameter"],
        "-CredentialExpiresAtEpoch",
        str(credential_expiration_epoch),
        "-HarnessRunId",
        harness_run_id,
        "-Scenario",
        scenario,
        "-ExecutionInputJson",
        context["execution_input"],
    ]
    process = subprocess.Popen(
        arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=safe_environment(credentials),
        creationflags=CREATE_NO_WINDOW,
    )
    started = time.monotonic()
    while True:
        remaining_seconds = parent_deadline_epoch - time.time()
        if remaining_seconds <= 0:
            process.terminate()
            try:
                process.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            try:
                stop_matching_harness_executions(
                    credentials, context["state_machine_arn"], harness_run_id
                )
            except Exception as error:
                category = str(error).split(":", 1)[0] or type(error).__name__
                emit(
                    f"HARNESS_EXECUTION_CLEANUP_FAILED name={scenario} "
                    f"category={category}"
                )
            emit(
                f"HARNESS_SCENARIO_FAILED name={scenario} "
                "category=CREDENTIAL_SAFETY_DEADLINE stage=CredentialSafetyStop"
            )
            return False
        try:
            stdout, stderr = process.communicate(
                timeout=min(45, max(1, remaining_seconds))
            )
            break
        except subprocess.TimeoutExpired:
            elapsed_minutes = int((time.monotonic() - started) // 60)
            emit(
                f"HARNESS_HEARTBEAT scenario={scenario} elapsed_minutes={elapsed_minutes}"
            )
    if process.returncode != 0:
        output = (stdout or "") + (stderr or "")
        try:
            stop_matching_harness_executions(
                credentials, context["state_machine_arn"], harness_run_id
            )
        except Exception as error:
            cleanup_category = str(error).split(":", 1)[0] or type(error).__name__
            emit(
                f"HARNESS_EXECUTION_CLEANUP_FAILED name={scenario} "
                f"category={cleanup_category}"
            )
        category = classify_harness_failure(output)
        stage = harness_failure_stage(output)
        emit(
            f"HARNESS_SCENARIO_FAILED name={scenario} category={category} stage={stage}"
        )
        return False
    emit(f"HARNESS_SCENARIO_PASSED name={scenario}")
    return True


def main_harness(scenarios: list[str]) -> int:
    source_credentials: dict[str, str] | None = None
    role_credentials: dict[str, str] | None = None
    baseline_ids: set[str] | None = None
    result = 1
    try:
        STATUS_PATH.unlink(missing_ok=True)
        access_key, secret_key, session_token = serve_credentials(
            "AWS dev Spot harness"
        )
        emit("CREDENTIALS_RECEIVED")
        source_credentials = {
            "AWS_ACCESS_KEY_ID": access_key,
            "AWS_SECRET_ACCESS_KEY": secret_key,
            "AWS_SESSION_TOKEN": session_token,
        }
        access_key = ""
        secret_key = ""
        session_token = ""
        role_credentials = assume_role(
            source_credentials["AWS_ACCESS_KEY_ID"],
            source_credentials["AWS_SECRET_ACCESS_KEY"],
            source_credentials["AWS_SESSION_TOKEN"],
        )
        for key in list(source_credentials):
            source_credentials[key] = ""
        source_credentials.clear()
        emit("DEV_ROLE_ASSUMED")
        state = pull_remote_state(role_credentials)
        context = derive_harness_context(state)
        del state
        baseline_ids = set(list_dev_workers(role_credentials))
        for scenario in scenarios:
            emit(f"HARNESS_SCENARIO_START name={scenario}")
            if not run_harness_scenario(role_credentials, context, scenario):
                result = 5
                break
        else:
            emit(f"DEV_HARNESS_COMPLETE scenarios={len(scenarios)}")
            result = 0
    except Exception as error:
        category = str(error).split(":", 1)[0] or type(error).__name__
        emit(f"DEV_HARNESS_FAILED category={category}")
        result = 1
    finally:
        cleanup_failed = False
        if role_credentials and baseline_ids is not None:
            try:
                cleanup_new_workers(role_credentials, baseline_ids)
            except Exception as error:
                cleanup_failed = True
                category = str(error).split(":", 1)[0] or type(error).__name__
                emit(f"HARNESS_CLEANUP_FAILED category={category}")
        for credentials in (source_credentials, role_credentials):
            if credentials:
                for key in list(credentials):
                    credentials[key] = ""
                credentials.clear()
        if cleanup_failed and result == 0:
            result = 1
    return result


def classify_history_cause(value: object) -> str:
    text = str(value or "").lower()
    categories: list[str] = []
    checks = (
        ("AUTHORIZATION", ("accessdenied", "unauthorized", "not authorized")),
        ("SPOT_CAPACITY", ("insufficientinstancecapacity", "unfulfillablecapacity")),
        ("SSM_COMMAND", ("ssm", "sendcommand", "commandinvocation")),
        ("TIMEOUT", ("timeout", "timedout", "timed out")),
        ("CONTAINER", ("docker", "container", "imagepull", "ecr")),
        ("DATABASE", ("postgres", "psycopg", "database")),
        ("SECRET", ("secretsmanager", "getsecretvalue")),
        ("AI_PROVIDER", ("upstage", "solar-pro")),
        ("RETRY_EXHAUSTED", ("retry budget exhausted", "crawlerattemptfailed")),
    )
    for category, needles in checks:
        if any(needle in text for needle in needles):
            categories.append(category)
    return ",".join(categories) if categories else "UNCLASSIFIED"


def classify_command_text(value: object) -> str:
    raw_text = str(value or "")
    text = raw_text.lower()
    categories: list[str] = []
    checks = (
        ("CRLF_SHELL", ("$'\\r'", "bash\\r", "^m", "invalid option name")),
        ("AWS_CLI_MISSING", ("aws: command not found", "aws: not found")),
        ("DOCKER_MISSING", ("docker: command not found", "docker: not found")),
        ("JQ_MISSING", ("jq: command not found", "jq: not found")),
        ("BASH_MISSING", ("bash: no such file", "bash: not found")),
        ("EXECUTABLE_MISSING", ("no such file or directory", "not found")),
        ("AUTHORIZATION", ("accessdenied", "not authorized", "permission denied")),
        ("ECR_AUTH", ("get-login-password", "no basic auth credentials")),
        ("IMAGE_PULL", ("manifest unknown", "pull access denied", "failed to pull")),
        (
            "PARAMETER_STORE",
            ("get-parameter", "parameter not found", "parameternotfound"),
        ),
        ("SECRET", ("getsecretvalue", "secretsmanager")),
        ("DATABASE", ("postgres", "psycopg", "database", "connection refused")),
        ("NETWORK", ("could not resolve", "name resolution", "network is unreachable")),
        ("TIMEOUT", ("timed out", "timeout")),
        ("DOCKER", ("docker", "container")),
        ("DISK", ("no space left", "disk quota")),
        ("SHELL", ("command not found", "syntax error", "unbound variable")),
    )
    for category, needles in checks:
        if any(needle in text for needle in needles):
            categories.append(category)
    if "\r" in raw_text and "CRLF_SHELL" not in categories:
        categories.append("CRLF_SHELL")
    return ",".join(categories) if categories else "UNCLASSIFIED"


def summarize_worker_result(value: object) -> str:
    try:
        payload = json.loads(str(value or ""))
    except (json.JSONDecodeError, TypeError):
        return "UNPARSEABLE"
    if not isinstance(payload, dict):
        return "UNPARSEABLE"
    status = str(payload.get("status", "UNKNOWN"))
    error_class = str(payload.get("error_class", "UNKNOWN"))
    if not re.fullmatch(r"[A-Z0-9_]{1,80}", status):
        status = "REDACTED"
    if not re.fullmatch(r"[A-Z0-9_]{1,80}", error_class):
        error_class = "REDACTED"
    return f"{status}:{error_class}"


def worker_result_run_id(value: object) -> str:
    try:
        payload = json.loads(str(value or ""))
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    run_id = str(payload.get("run_id", ""))
    return run_id if re.fullmatch(r"[A-Za-z0-9_-]{1,96}", run_id) else ""


def summarize_failure_log(value: object) -> str:
    raw_text = str(value or "")
    crawler_types = re.findall(r"\b([A-E]) 타입 시작\b", raw_text)
    exception_types = sorted(
        set(
            re.findall(
                r"\b([A-Za-z_][A-Za-z0-9_.]{0,80}(?:Error|Exception))\b",
                raw_text,
            )
        )
    )[:8]
    phase_markers = (
        ("CRAWLING", "타입 시작"),
        ("UNIFICATION", "데이터 통합 시작"),
        ("AI_PROCESSING", "AI 전처리 시작"),
        ("DB_LOAD", "DB 적재 시작"),
        ("DONE", "전체 공정 완료"),
    )
    last_phase = "UNKNOWN"
    last_position = -1
    for phase, marker in phase_markers:
        position = raw_text.rfind(marker)
        if position > last_position:
            last_phase = phase
            last_position = position
    error_lines = sum(
        1
        for line in raw_text.splitlines()
        if "crawler failed:" in line or "크롤러 실행 실패:" in line
    )
    value_error_messages = (
        ("ATTACHMENTS_NOT_LIST", "attachments must be a list"),
        ("ATTACHMENT_NOT_OBJECT", "each attachment must be an object"),
        (
            "ATTACHMENT_NOT_EXTERNAL_URL",
            "crawler attachments must be EXTERNAL file_url objects",
        ),
        ("ATTACHMENT_URL_MISSING", "attachment file_url is required"),
        ("CRAWLER_RECORD_NOT_OBJECT", "crawler record must be an object"),
        ("QUEUE_RECORD_NOT_OBJECT", "queue record must be an object"),
        ("NON_SCHOOL_RECORD", "crawler writer accepts SCHOOL records only"),
        (
            "SIMILARITY_IDENTITY_MISSING",
            "similarity must contain score and candidate source identity",
        ),
        ("SIMILARITY_SCORE_NOT_NUMERIC", "similarity score must be numeric"),
        (
            "SIMILARITY_SCORE_OUT_OF_RANGE",
            "similarity score must be between 0 and 100",
        ),
        ("QUEUE_ROOT_NOT_LIST", "queue JSON root must be a list"),
        ("QUEUE_MODE_UNSUPPORTED", "unsupported queue mode"),
    )
    value_error_reason = next(
        (label for label, message in value_error_messages if message in raw_text),
        "UNCLASSIFIED",
    )
    if value_error_reason == "UNCLASSIFIED":
        field_error = re.search(
            r"\b(source_type|vendor_initial|external_key|source_url|title|content|"
            r"start_date|due_date|published_at|category_code) "
            r"(is required|must be an ISO date or timestamp string)\b",
            raw_text,
        )
        if field_error:
            suffix = (
                "REQUIRED"
                if field_error.group(2) == "is required"
                else "INVALID_DATE_TYPE"
            )
            value_error_reason = f"{field_error.group(1).upper()}_{suffix}"
    return (
        f"last_crawler={crawler_types[-1] if crawler_types else 'UNKNOWN'} "
        f"last_phase={last_phase} "
        f"exceptions={','.join(exception_types) if exception_types else 'NONE'} "
        f"classified_error_lines={error_lines} "
        f"value_error_reason={value_error_reason}"
    )


def summarize_authorization_detail(value: object) -> str:
    raw_text = str(value or "")
    operations = re.findall(
        r"when calling the ([A-Za-z0-9]+) operation", raw_text, re.IGNORECASE
    )
    actions = re.findall(
        r"(?:perform|action):\s*([a-z0-9-]+:[A-Za-z0-9*]+)",
        raw_text,
        re.IGNORECASE,
    )
    safe = []
    for value_part in operations + actions:
        if re.fullmatch(r"[A-Za-z0-9*_.:-]{1,120}", value_part):
            safe.append(value_part)
    return ",".join(dict.fromkeys(safe)) if safe else "UNCLASSIFIED"


def summarize_bootstrap_stage(value: object) -> str:
    match = re.search(
        r"\bWORKER_BOOTSTRAP_FAILURE="
        r"(INSTANCE_READINESS|RUNTIME_PARAMETER|IMAGE_PREPARATION)\b",
        str(value or ""),
    )
    return match.group(1) if match else "UNCLASSIFIED"


def main_diagnose_latest() -> int:
    credentials: dict[str, str] | None = None
    try:
        STATUS_PATH.unlink(missing_ok=True)
        access_key, secret_key, session_token = serve_credentials(
            "AWS dev latest harness diagnosis"
        )
        emit("CREDENTIALS_RECEIVED")
        try:
            credentials = assume_role(access_key, secret_key, session_token)
        finally:
            access_key = ""
            secret_key = ""
            session_token = ""
        emit("DEV_ROLE_ASSUMED")
        state = pull_remote_state(credentials)
        context = derive_harness_context(state)
        del state
        response = aws_json(
            [
                "stepfunctions",
                "list-executions",
                "--state-machine-arn",
                context["state_machine_arn"],
                "--max-results",
                "25",
            ],
            credentials,
        )
        executions = (
            response.get("executions", []) if isinstance(response, dict) else []
        )
        candidates = [
            execution
            for execution in executions
            if isinstance(execution, dict)
            and str(execution.get("name", "")).startswith("harness-")
            and execution.get("executionArn")
        ]
        if not candidates:
            raise RuntimeError("LATEST_HARNESS_NOT_FOUND")
        execution_arn = str(candidates[0]["executionArn"])
        execution = aws_json(
            [
                "stepfunctions",
                "describe-execution",
                "--execution-arn",
                execution_arn,
            ],
            credentials,
        )
        status = str(execution.get("status", "")) if isinstance(execution, dict) else ""
        emit(f"DEV_DIAGNOSTIC_EXECUTION status={status or 'UNKNOWN'}")
        terminal_error = (
            str(execution.get("error", "")) if isinstance(execution, dict) else ""
        )
        safe_terminal_error = (
            terminal_error
            if re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", terminal_error)
            else "REDACTED_OR_EMPTY"
        )
        terminal_cause = (
            str(execution.get("cause", "")) if isinstance(execution, dict) else ""
        )
        emit(
            "DEV_DIAGNOSTIC_TERMINAL "
            f"error={safe_terminal_error} "
            f"category={classify_history_cause(terminal_cause + ' ' + terminal_error)}"
        )
        try:
            history = aws_json(
                [
                    "stepfunctions",
                    "get-execution-history",
                    "--execution-arn",
                    execution_arn,
                    "--reverse-order",
                    "--max-results",
                    "1000",
                ],
                credentials,
            )
            events = (
                list(reversed(history.get("events", [])))
                if isinstance(history, dict)
                else []
            )
        except RuntimeError as error:
            emit(
                "DEV_DIAGNOSTIC_HISTORY_UNAVAILABLE "
                f"category={str(error).split(':', 1)[0]}"
            )
            events = []
        recent_states: list[str] = []
        failure_type = "NONE"
        failure_error = "NONE"
        failure_category = "NONE"
        command_results: list[dict[str, object]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            entered = event.get("stateEnteredEventDetails")
            if isinstance(entered, dict) and entered.get("name"):
                recent_states.append(str(entered["name"]))
            exited = event.get("stateExitedEventDetails")
            if isinstance(exited, dict) and exited.get("name") == "GetCommandResult":
                try:
                    payload = json.loads(str(exited.get("output", "")))
                except json.JSONDecodeError:
                    payload = {}
                command = (
                    payload.get("Command", {}) if isinstance(payload, dict) else {}
                )
                if isinstance(command, dict):
                    stdout = str(command.get("StandardOutputContent", ""))
                    stderr = str(command.get("StandardErrorContent", ""))
                    command_results.append(
                        {
                            "status": str(command.get("Status", "UNKNOWN")),
                            "response_code": command.get("ResponseCode", "UNKNOWN"),
                            "stdout_category": classify_command_text(stdout),
                            "stderr_category": classify_command_text(stderr),
                            "worker_result": summarize_worker_result(stdout),
                            "run_id": worker_result_run_id(stdout),
                            "authorization_detail": summarize_authorization_detail(
                                stderr
                            ),
                            "bootstrap_stage": summarize_bootstrap_stage(stderr),
                            "stdout_bytes": len(stdout.encode("utf-8")),
                            "stderr_bytes": len(stderr.encode("utf-8")),
                        }
                    )
            for detail_name in (
                "taskFailedEventDetails",
                "executionFailedEventDetails",
                "executionTimedOutEventDetails",
                "executionAbortedEventDetails",
            ):
                details = event.get(detail_name)
                if not isinstance(details, dict):
                    continue
                failure_type = detail_name
                raw_error = str(details.get("error", ""))
                failure_error = (
                    raw_error
                    if re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", raw_error)
                    else "REDACTED_OR_EMPTY"
                )
                failure_category = classify_history_cause(
                    str(details.get("cause", "")) + " " + raw_error
                )
        safe_states = [
            name
            for name in recent_states[-12:]
            if re.fullmatch(r"[A-Za-z0-9_.:-]+", name)
        ]
        emit("DEV_DIAGNOSTIC_RECENT_STATES names=" + ",".join(safe_states))
        for index, command in enumerate(command_results[-3:], start=1):
            emit(
                "DEV_DIAGNOSTIC_COMMAND "
                f"sample={index} status={command['status']} "
                f"response_code={command['response_code']} "
                f"stdout_category={command['stdout_category']} "
                f"stderr_category={command['stderr_category']} "
                f"worker_result={command['worker_result']} "
                f"authorization_detail={command['authorization_detail']} "
                f"bootstrap_stage={command['bootstrap_stage']} "
                f"stdout_bytes={command['stdout_bytes']} "
                f"stderr_bytes={command['stderr_bytes']}"
            )
        latest_run_id = next(
            (
                str(command.get("run_id", ""))
                for command in reversed(command_results)
                if command.get("run_id")
            ),
            "",
        )
        if latest_run_id:
            artifact_keys = find_failure_artifact_keys(
                context["state_bucket"], latest_run_id, credentials
            )
            metadata_key = artifact_keys.get("metadata", "")
            metadata_text, metadata_category = (
                aws_s3_object_text(context["state_bucket"], metadata_key, credentials)
                if metadata_key
                else (None, "NOT_FOUND")
            )
            if metadata_text is not None:
                try:
                    metadata = json.loads(metadata_text)
                except json.JSONDecodeError:
                    metadata = {}
                exit_code = metadata.get("exit_code", "UNKNOWN")
                if not isinstance(exit_code, int):
                    exit_code = "UNKNOWN"
                emit(
                    "DEV_DIAGNOSTIC_ARTIFACT "
                    f"exit_code={exit_code} "
                    f"db_committed={bool(metadata.get('db_committed', False))} "
                    "history_committed="
                    f"{bool(metadata.get('history_committed', False))}"
                )
            else:
                emit(
                    f"DEV_DIAGNOSTIC_ARTIFACT_UNAVAILABLE category={metadata_category}"
                )
            worker_log_key = artifact_keys.get("worker_log", "")
            worker_log, log_category = (
                aws_s3_object_text(context["state_bucket"], worker_log_key, credentials)
                if worker_log_key
                else (None, "NOT_FOUND")
            )
            if worker_log is not None:
                emit("DEV_DIAGNOSTIC_LOG " + summarize_failure_log(worker_log))
            else:
                emit(f"DEV_DIAGNOSTIC_LOG_UNAVAILABLE category={log_category}")
            emit(
                "DEV_DIAGNOSTIC_QUEUE "
                + summarize_failure_queues(
                    context["state_bucket"], latest_run_id, credentials
                )
            )
        emit(
            "DEV_DIAGNOSTIC_FAILURE "
            f"type={failure_type} error={failure_error} category={failure_category}"
        )
        workers = list_dev_workers(credentials)
        state_counts: dict[str, int] = {}
        for worker_state in workers.values():
            state_counts[worker_state] = state_counts.get(worker_state, 0) + 1
        worker_summary = ",".join(
            f"{name}:{count}" for name, count in sorted(state_counts.items())
        )
        emit(
            f"DEV_DIAGNOSTIC_WORKERS total={len(workers)} states={worker_summary or 'none'}"
        )
        emit("DEV_DIAGNOSTIC_COMPLETE")
        return 0
    except Exception as error:
        category = str(error).split(":", 1)[0] or type(error).__name__
        emit(f"DEV_DIAGNOSTIC_FAILED category={category}")
        return 1
    finally:
        if credentials:
            for key in list(credentials):
                credentials[key] = ""
            credentials.clear()


def main_diagnose_recent_overlap() -> int:
    """Summarize the two newest harness executions without exposing identifiers."""
    credentials: dict[str, str] | None = None
    try:
        STATUS_PATH.unlink(missing_ok=True)
        access_key, secret_key, session_token = serve_credentials(
            "AWS dev recent overlap diagnosis"
        )
        emit("CREDENTIALS_RECEIVED")
        try:
            credentials = assume_role(access_key, secret_key, session_token)
        finally:
            access_key = ""
            secret_key = ""
            session_token = ""
        emit("DEV_ROLE_ASSUMED")
        state = pull_remote_state(credentials)
        context = derive_harness_context(state)
        del state
        response = aws_json(
            [
                "stepfunctions",
                "list-executions",
                "--state-machine-arn",
                context["state_machine_arn"],
                "--max-results",
                "10",
            ],
            credentials,
        )
        executions = (
            response.get("executions", []) if isinstance(response, dict) else []
        )
        candidates = [
            execution
            for execution in executions
            if isinstance(execution, dict)
            and str(execution.get("name", "")).startswith("harness-")
            and execution.get("executionArn")
        ]
        if len(candidates) < 2:
            raise RuntimeError(f"RECENT_HARNESS_COUNT_{len(candidates)}")
        for ordinal, candidate in enumerate(candidates[:2], start=1):
            execution = aws_json(
                [
                    "stepfunctions",
                    "describe-execution",
                    "--execution-arn",
                    str(candidate["executionArn"]),
                ],
                credentials,
            )
            status = str(execution.get("status", "UNKNOWN"))
            output = str(execution.get("output", ""))
            error = str(execution.get("error", ""))
            cause = str(execution.get("cause", ""))
            if "SKIPPED_OVERLAP" in output:
                outcome = "SKIPPED_OVERLAP"
            elif "SUCCESS" in output:
                outcome = "SUCCESS"
            elif output:
                outcome = "OTHER_OUTPUT"
            else:
                outcome = "NO_OUTPUT"
            emit(
                "DEV_OVERLAP_EXECUTION "
                f"ordinal={ordinal} status={status} outcome={outcome} "
                f"failure_category={classify_history_cause(cause + ' ' + error)}"
            )
        workers = list_dev_workers(credentials)
        state_counts: dict[str, int] = {}
        for worker_state in workers.values():
            state_counts[worker_state] = state_counts.get(worker_state, 0) + 1
        worker_summary = ",".join(
            f"{name}:{count}" for name, count in sorted(state_counts.items())
        )
        emit(
            f"DEV_DIAGNOSTIC_WORKERS total={len(workers)} states={worker_summary or 'none'}"
        )
        emit("DEV_OVERLAP_DIAGNOSTIC_COMPLETE")
        return 0
    except Exception as error:
        category = str(error).split(":", 1)[0] or type(error).__name__
        emit(f"DEV_OVERLAP_DIAGNOSTIC_FAILED category={category}")
        return 1
    finally:
        if credentials:
            for key in list(credentials):
                credentials[key] = ""
            credentials.clear()


def main_cleanup_recent_overlap() -> int:
    """Stop exactly one orphaned dev harness execution and its worker."""
    credentials: dict[str, str] | None = None
    try:
        STATUS_PATH.unlink(missing_ok=True)
        access_key, secret_key, session_token = serve_credentials(
            "AWS dev approved overlap cleanup"
        )
        emit("CREDENTIALS_RECEIVED")
        try:
            credentials = assume_role(access_key, secret_key, session_token)
        finally:
            access_key = ""
            secret_key = ""
            session_token = ""
        emit("DEV_ROLE_ASSUMED")

        state = pull_remote_state(credentials)
        context = derive_harness_context(state)
        del state
        response = aws_json(
            [
                "stepfunctions",
                "list-executions",
                "--state-machine-arn",
                context["state_machine_arn"],
                "--status-filter",
                "RUNNING",
                "--max-results",
                "25",
            ],
            credentials,
        )
        executions = (
            response.get("executions", []) if isinstance(response, dict) else []
        )
        candidates = [
            execution
            for execution in executions
            if isinstance(execution, dict)
            and str(execution.get("name", "")).startswith("harness-")
            and execution.get("executionArn")
        ]
        workers = list_dev_workers(credentials)
        active_workers = [
            instance_id
            for instance_id, state_name in workers.items()
            if state_name in {"pending", "running"}
        ]
        if len(candidates) > 1:
            raise RuntimeError(f"CLEANUP_RUNNING_HARNESS_COUNT_{len(candidates)}")
        if len(active_workers) != 1:
            raise RuntimeError(f"CLEANUP_ACTIVE_WORKER_COUNT_{len(active_workers)}")

        execution_arn = str(candidates[0]["executionArn"]) if candidates else None
        worker_id = active_workers[0]
        if execution_arn:
            try:
                aws_json(
                    [
                        "stepfunctions",
                        "stop-execution",
                        "--execution-arn",
                        execution_arn,
                        "--error",
                        "ApprovedManualCleanup",
                        "--cause",
                        "Approved cleanup after local harness observer failure",
                    ],
                    credentials,
                )
            except Exception as error:
                category = str(error).split(":", 1)[0] or type(error).__name__
                raise RuntimeError(f"CLEANUP_STOP_EXECUTION_{category}") from error
        try:
            aws_json(
                ["ec2", "terminate-instances", "--instance-ids", worker_id],
                credentials,
            )
        except Exception as error:
            category = str(error).split(":", 1)[0] or type(error).__name__
            raise RuntimeError(f"CLEANUP_TERMINATE_WORKER_{category}") from error
        emit(
            "DEV_OVERLAP_CLEANUP_REQUESTED "
            f"executions={1 if execution_arn else 0} workers=1"
        )

        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            execution_status = "NOT_RUNNING"
            if execution_arn:
                execution = aws_json(
                    [
                        "stepfunctions",
                        "describe-execution",
                        "--execution-arn",
                        execution_arn,
                    ],
                    credentials,
                )
                execution_status = (
                    str(execution.get("status", "UNKNOWN"))
                    if isinstance(execution, dict)
                    else "UNKNOWN"
                )
            worker_present = worker_id in list_dev_workers(credentials)
            if execution_status != "RUNNING" and not worker_present:
                emit(
                    "DEV_OVERLAP_CLEANUP_COMPLETE "
                    f"execution_status={execution_status} workers=0"
                )
                return 0
            emit(
                "DEV_OVERLAP_CLEANUP_WAIT "
                f"execution_running={str(execution_status == 'RUNNING').lower()} "
                f"worker_present={str(worker_present).lower()}"
            )
            time.sleep(30)
        raise RuntimeError("DEV_OVERLAP_CLEANUP_TIMEOUT")
    except Exception as error:
        category = str(error).split(":", 1)[0] or type(error).__name__
        emit(f"DEV_OVERLAP_CLEANUP_FAILED category={category}")
        return 1
    finally:
        if credentials:
            for key in list(credentials):
                credentials[key] = ""
            credentials.clear()


def main_observe_running() -> int:
    credentials: dict[str, str] | None = None
    try:
        STATUS_PATH.unlink(missing_ok=True)
        access_key, secret_key, session_token = serve_credentials(
            "AWS dev Step Functions observation"
        )
        emit("CREDENTIALS_RECEIVED")
        try:
            credentials = assume_role(access_key, secret_key, session_token)
        finally:
            access_key = ""
            secret_key = ""
            session_token = ""
        emit("DEV_ROLE_ASSUMED")
        state = pull_remote_state(credentials)
        context = derive_harness_context(state)
        del state
        response = aws_json(
            [
                "stepfunctions",
                "list-executions",
                "--state-machine-arn",
                context["state_machine_arn"],
                "--status-filter",
                "RUNNING",
                "--max-results",
                "10",
            ],
            credentials,
        )
        executions = (
            response.get("executions", []) if isinstance(response, dict) else []
        )
        candidates = [
            execution
            for execution in executions
            if isinstance(execution, dict)
            and str(execution.get("name", "")).startswith("harness-")
            and execution.get("executionArn")
        ]
        if len(candidates) != 1:
            raise RuntimeError(f"RUNNING_HARNESS_COUNT_{len(candidates)}")
        execution_arn = str(candidates[0]["executionArn"])
        emit("DEV_OBSERVER_ATTACHED running_harness_count=1")
        started = time.monotonic()
        while True:
            execution = aws_json(
                [
                    "stepfunctions",
                    "describe-execution",
                    "--execution-arn",
                    execution_arn,
                ],
                credentials,
            )
            status = (
                str(execution.get("status", "")) if isinstance(execution, dict) else ""
            )
            if status != "RUNNING":
                emit(f"DEV_EXECUTION_TERMINAL status={status or 'UNKNOWN'}")
                return 0 if status == "SUCCEEDED" else 5
            elapsed_minutes = int((time.monotonic() - started) // 60)
            emit(f"DEV_OBSERVER_HEARTBEAT elapsed_minutes={elapsed_minutes}")
            time.sleep(45)
    except Exception as error:
        category = str(error).split(":", 1)[0] or type(error).__name__
        emit(f"DEV_OBSERVER_FAILED category={category}")
        return 1
    finally:
        if credentials:
            for key in list(credentials):
                credentials[key] = ""
            credentials.clear()


def serve_credentials(purpose: str = "AWS dev Terraform plan") -> tuple[str, str, str]:
    token = secrets.token_urlsafe(24)
    submitted: dict[str, str] = {}
    ready = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def headers_common(self) -> None:
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'",
            )

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            supplied = parse_qs(parsed.query).get("token", [""])[0]
            if parsed.path != "/" or not secrets.compare_digest(supplied, token):
                self.send_error(404)
                return
            safe_purpose = html.escape(purpose)
            body = f"""<!doctype html><html lang=ko><meta charset=utf-8><title>{safe_purpose}</title>
<style>body{{font:16px system-ui;max-width:640px;margin:48px auto;padding:0 20px}}label{{display:block;margin:16px 0 6px}}input{{box-sizing:border-box;width:100%;padding:10px}}button{{margin-top:22px;padding:10px 18px}}</style>
<h1>{safe_purpose}</h1><p>기본 IAM 자격증명을 입력하면 dev 역할로 전환합니다. 값은 파일에 저장되지 않습니다.</p>
<form method=post action="/submit?token={html.escape(token)}" autocomplete=off>
<label>Access key ID</label><input name=access_key required spellcheck=false>
<label>Secret access key</label><input name=secret_key type=password required>
<label>Session token (있는 경우만)</label><input name=session_token type=password>
<button type=submit>제출하고 plan 실행</button></form></html>""".encode()
            self.send_response(200)
            self.headers_common()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            supplied = parse_qs(parsed.query).get("token", [""])[0]
            if parsed.path != "/submit" or not secrets.compare_digest(supplied, token):
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > 16384:
                self.send_error(400)
                return
            data = parse_qs(
                self.rfile.read(length).decode("utf-8"), keep_blank_values=True
            )
            access_key = data.get("access_key", [""])[0].strip()
            secret_key = data.get("secret_key", [""])[0].strip()
            session_token = data.get("session_token", [""])[0].strip()
            if not access_key or not secret_key:
                self.send_error(400)
                return
            submitted.update(
                access_key=access_key,
                secret_key=secret_key,
                session_token=session_token,
            )
            body = "자격증명을 받았습니다. 이 탭을 닫고 Codex로 돌아가 주세요.".encode()
            self.send_response(200)
            self.headers_common()
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            ready.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(
        f"CREDENTIAL_FORM_URL=http://127.0.0.1:{server.server_port}/?token={token}",
        flush=True,
    )
    ready.wait()
    server.shutdown()
    server.server_close()
    return submitted["access_key"], submitted["secret_key"], submitted["session_token"]


def await_control(allowed_commands: set[str]) -> str:
    token = secrets.token_urlsafe(24)
    selected: dict[str, str] = {}
    ready = threading.Event()
    consumption_lock = threading.Lock()
    consumed = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_POST(self) -> None:
            nonlocal consumed
            parsed = urlparse(self.path)
            supplied = parse_qs(parsed.query).get("token", [""])[0]
            command = parsed.path.removeprefix("/").lower()
            if (
                not secrets.compare_digest(supplied, token)
                or command not in allowed_commands
            ):
                self.send_error(404)
                return
            with consumption_lock:
                if consumed:
                    self.send_error(404)
                    return
                consumed = True
                selected["command"] = command
            body = b"accepted"
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            ready.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    commands = "|".join(sorted(allowed_commands))
    print(
        f"CONTROL_URL=http://127.0.0.1:{server.server_port} "
        f"token={token} commands={commands}",
        flush=True,
    )
    while not ready.wait(timeout=30):
        emit("CONTROL_HEARTBEAT waiting=true")
    server.shutdown()
    server.server_close()
    return selected["command"]


def main_plan() -> int:
    credentials: dict[str, str] | None = None
    try:
        STATUS_PATH.unlink(missing_ok=True)
        access_key, secret_key, session_token = serve_credentials()
        emit("CREDENTIALS_RECEIVED")
        try:
            credentials = assume_role(access_key, secret_key, session_token)
        finally:
            access_key = ""
            secret_key = ""
            session_token = ""
        emit("DEV_ROLE_ASSUMED")
        if not execute_plan(credentials):
            cleanup_volume()
            return 2
        emit("AWAITING_APPLY_APPROVAL command=apply|cancel")
        command = await_control({"apply", "cancel"})
        if command == "cancel":
            cleanup_volume()
            emit("DEV_PLAN_CANCELLED")
            return 0
        if not execute_apply(credentials):
            cleanup_volume()
            return 4
        emit("AWAITING_POST_APPLY command=finish")
        await_control({"finish"})
        cleanup_volume()
        emit("DEV_COORDINATOR_FINISHED")
        return 0
    except Exception as error:
        category = str(error).split(":", 1)[0] or type(error).__name__
        emit(f"DEV_COORDINATOR_FAILED category={category}")
        try:
            cleanup_volume()
        except Exception as cleanup_error:
            cleanup_category = (
                str(cleanup_error).split(":", 1)[0] or type(cleanup_error).__name__
            )
            emit(f"PLAN_VOLUME_CLEANUP_FAILED category={cleanup_category}")
        return 1
    finally:
        if credentials:
            for key in list(credentials):
                credentials[key] = ""
            credentials.clear()


def main_release(reuse_existing_image: bool = False) -> int:
    source_credentials: dict[str, str] | None = None
    role_credentials: dict[str, str] | None = None
    baseline_ids: set[str] | None = None
    result = 1
    try:
        STATUS_PATH.unlink(missing_ok=True)
        credential_title = (
            "AWS dev Solar Pro 4 existing-image rollout"
            if reuse_existing_image
            else "AWS dev Solar Pro 4 release"
        )
        access_key, secret_key, session_token = serve_credentials(credential_title)
        emit("CREDENTIALS_RECEIVED")
        source_credentials = {
            "AWS_ACCESS_KEY_ID": access_key,
            "AWS_SECRET_ACCESS_KEY": secret_key,
            "AWS_SESSION_TOKEN": session_token,
        }
        access_key = ""
        secret_key = ""
        session_token = ""
        if reuse_existing_image:
            image_ref, repository_arn, git_sha = resolve_existing_image(
                source_credentials
            )
        else:
            image_ref, repository_arn, git_sha = publish_image(source_credentials)
        role_credentials = assume_role(
            source_credentials["AWS_ACCESS_KEY_ID"],
            source_credentials["AWS_SECRET_ACCESS_KEY"],
            source_credentials["AWS_SESSION_TOKEN"],
        )
        for key in list(source_credentials):
            source_credentials[key] = ""
        source_credentials.clear()
        emit("DEV_ROLE_ASSUMED")
        if not execute_plan(
            role_credentials,
            {
                "crawler_image_ref": image_ref,
                "crawler_ecr_repository_arn": repository_arn,
                "crawler_git_sha": git_sha,
            },
            FULL_ROLLOUT_UPDATE_ADDRESSES if reuse_existing_image else None,
        ):
            cleanup_volume()
            result = 2
        else:
            emit("AWAITING_APPLY_APPROVAL command=apply|cancel")
            command = await_control({"apply", "cancel"})
            if command == "cancel":
                cleanup_volume()
                emit("DEV_RELEASE_CANCELLED")
                result = 0
            elif not execute_apply(role_credentials):
                cleanup_volume()
                result = 4
            else:
                state = pull_remote_state(role_credentials)
                context = derive_harness_context(state)
                del state
                baseline_ids = set(list_dev_workers(role_credentials))
                for scenario in ("ValidateInfrastructure", "Success"):
                    emit(f"HARNESS_SCENARIO_START name={scenario}")
                    if not run_harness_scenario(role_credentials, context, scenario):
                        result = 5
                        break
                else:
                    emit("DEV_RELEASE_COMPLETE smoke=true schedule_enabled=false")
                    result = 0
    except Exception as error:
        category = str(error).split(":", 1)[0] or type(error).__name__
        emit(f"DEV_RELEASE_FAILED category={category}")
        result = 1
    finally:
        cleanup_failed = False
        if role_credentials and baseline_ids is not None:
            try:
                cleanup_new_workers(role_credentials, baseline_ids)
            except Exception as error:
                cleanup_failed = True
                category = str(error).split(":", 1)[0] or type(error).__name__
                emit(f"HARNESS_CLEANUP_FAILED category={category}")
        try:
            cleanup_volume()
        except Exception as error:
            cleanup_failed = True
            category = str(error).split(":", 1)[0] or type(error).__name__
            emit(f"PLAN_VOLUME_CLEANUP_FAILED category={category}")
        for credentials in (source_credentials, role_credentials):
            if credentials:
                for key in list(credentials):
                    credentials[key] = ""
                credentials.clear()
        if cleanup_failed and result == 0:
            result = 1
    return result


atexit.register(cleanup_volume_at_exit)

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "observe-running":
        raise SystemExit(main_observe_running())
    if len(sys.argv) >= 2 and sys.argv[1] == "diagnose-latest":
        raise SystemExit(main_diagnose_latest())
    if len(sys.argv) >= 2 and sys.argv[1] == "diagnose-recent-overlap":
        raise SystemExit(main_diagnose_recent_overlap())
    if len(sys.argv) >= 2 and sys.argv[1] == "cleanup-recent-overlap":
        raise SystemExit(main_cleanup_recent_overlap())
    if len(sys.argv) >= 2 and sys.argv[1] == "harness-scenario":
        allowed_scenarios = {
            "ValidateInfrastructure",
            "CapacityFallback",
            "LockExpiry",
            "Heartbeat",
            "Success",
            "Overlap",
            "TransientRetry",
            "SpotInterruption",
            "Timeout",
        }
        if len(sys.argv) != 3 or sys.argv[2] not in allowed_scenarios:
            emit("HARNESS_SCENARIO_ARGUMENT_INVALID")
            raise SystemExit(2)
        raise SystemExit(main_harness([sys.argv[2]]))
    if len(sys.argv) >= 2 and sys.argv[1] == "release-smoke":
        raise SystemExit(main_release())
    if len(sys.argv) >= 2 and sys.argv[1] == "deploy-existing-smoke":
        raise SystemExit(main_release(reuse_existing_image=True))
    raise SystemExit(main_plan())
