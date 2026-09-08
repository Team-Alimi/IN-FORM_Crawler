# IN-FORM crawler AWS infrastructure

This Terraform root implements the owner-approved v11 durable-state and
scheduler/Spot contracts. Creating these source files does not authorize
`terraform apply`, a real AWS harness run, image publication, or production release.

## Layout

- `modules/state`: private versioned SSE-S3 state bucket and DynamoDB lease table.
- `modules/network`: no-ingress crawler security group and private PostgreSQL rule.
- `modules/iam`: separate runtime, orchestration, and Scheduler roles.
- `modules/spot`: disposable Amazon Linux 2023 launch template and SSM worker command.
- `modules/scheduler`: EventBridge Scheduler and Step Functions control plane.
- `environments/dev`: disabled-by-default non-production composition.
- `environments/prod`: disabled-by-default production composition; apply is separately gated.
- `harness`: explicit, identity-checked real-AWS dev acceptance harness.

The implementation keeps the owner-approved constants: 06:00 Asia/Seoul,
20-minute lease, 5-minute heartbeat, three attempts with 10/30-minute delays,
90-minute warning, 120-minute hard timeout, and `price-capacity-optimized`
allocation across at least two subnets and two x86_64 instance types.

Environment identifiers belong in uncommitted `*.tfvars` files. Never store
credentials or secret values here. `database_secret_arn` identifies the one
approved Secrets Manager object; `crawler_image_ref` must be an immutable digest.

## Offline checks

```powershell
python -m unittest tests.contract.test_aws_terraform_contract -v
terraform fmt -check -recursive infra/aws/crawler
```

`terraform init/validate/plan` can require provider downloads and backend/AWS
configuration. The real harness is intentionally not an offline test.
