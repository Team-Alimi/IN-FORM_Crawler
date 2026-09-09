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
- `harness`: explicit, identity-checked real-AWS dev acceptance harness plus template-only IAM
  handoff for the separated dev Terraform role.

The implementation keeps the owner-approved constants: 06:00 Asia/Seoul,
20-minute lease, 5-minute heartbeat, three attempts with 10/30-minute delays,
90-minute warning, 120-minute hard timeout, and `price-capacity-optimized`
allocation across at least two subnets and two x86_64 instance types.

Environment identifiers belong in uncommitted `*.tfvars` files. Never store
credentials or secret values here. `database_secret_arn` identifies the one
approved Secrets Manager object; `crawler_image_ref` must be an immutable digest,
and `crawler_ecr_repository_arn` scopes runtime pull access to that repository.

## Remote Terraform state

Both environment roots use a partial S3 backend with S3 native lockfiles. The
pre-existing Terraform-state bucket must be private, encrypted, versioned, and
must not be the crawler durable-state bucket or another application's data bucket.
It is a bootstrap/platform dependency and is not created by these environment roots.

Inject only non-secret physical backend settings during initialization. Keep AWS
credentials in the standard AWS profile/environment credential chain, never in
`-backend-config` arguments or committed files. Use a distinct key for each environment:

```powershell
terraform -chdir=infra/aws/crawler/environments/dev init -backend-config="bucket=<terraform-state-bucket>" -backend-config="key=inform-crawler/dev/terraform.tfstate" -backend-config="region=<aws-region>"
terraform -chdir=infra/aws/crawler/environments/prod init -backend-config="bucket=<terraform-state-bucket>" -backend-config="key=inform-crawler/prod/terraform.tfstate" -backend-config="region=<aws-region>"
```

S3 native locking requires Terraform 1.10 or newer. The roots constrain Terraform
to `>= 1.10.0, < 2.0.0`.

The dev and prod `.terraform.lock.hcl` files are committed and intentionally
identical so provider installation is reproducible. Provider upgrades must update
both lockfiles together and pass both environment validations before review.

## Offline checks

```powershell
python -m unittest tests.contract.test_aws_terraform_contract -v
terraform fmt -check -recursive infra/aws/crawler
```

`terraform init/validate/plan` can require provider downloads and backend/AWS
configuration. Offline validation may use `terraform init -backend=false`. The
real harness is intentionally not an offline test.
