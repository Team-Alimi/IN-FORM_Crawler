# Real AWS dev harness

This harness is the non-production acceptance driver required by the v11
durable-state and Scheduler/Spot contracts. It is intentionally identity-gated
and refuses resource names that do not identify `dev`.

Running it contacts AWS and changes dev resources. Source creation is approved;
execution still requires a separately scoped approval, an authenticated AWS CLI,
an applied dev Terraform stack, a dev-only database guard parameter, and an
immutable published crawler image.

The `ValidateInfrastructure` scenario checks account/region identity, dev naming,
the production-DB denial guard, S3 encryption/versioning/public block/lifecycle,
the DynamoDB lock table, disabled dev schedule, and the Step Functions definition.
Execution scenarios use the Terraform `manual_execution_input` output and cover
success, overlap, lease expiry, heartbeat, transient retry, timeout, interruption,
and candidate-pool fallback. They never use production state or credentials.

Example shape (replace placeholders locally; do not commit them):

```powershell
./run-dev.ps1 `
  -ExpectedAccountId '<12-digit-account>' `
  -ExpectedRegion 'ap-northeast-2' `
  -DevStateBucket 'inform-crawler-state-dev-<suffix>' `
  -DevLockTable 'inform-crawler-runtime-lock-dev' `
  -DevSchedulerName 'inform-crawler-scheduler-dev' `
  -DevStateMachineArn '<dev-state-machine-arn>' `
  -DevDbGuardParameter '/inform/crawler/dev/PRODUCTION_DB_ACCESS_ALLOWED' `
  -Scenario ValidateInfrastructure
```

Do not put secret values in command history, Terraform outputs, harness output,
or this directory.
