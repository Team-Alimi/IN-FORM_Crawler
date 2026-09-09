# Dev Terraform deployment identity handoff

These templates implement the approved separation between the existing ECR publisher IAM user and
the `inform-crawler-terraform-dev` role. They are review inputs only and must not be applied without
explicit approval. Creating the role, attaching either policy, creating the backend bucket, running
Terraform plan/apply, and executing the real harness are separate AWS mutation/approval gates.

## Boundary

- The existing publisher user receives only `sts:AssumeRole` for the dev Terraform role.
- The role trust policy names only that existing user. The role has no access key and no console
  password.
- The role permission template covers the current dev Terraform resource types and the dev remote
  state key. It deliberately excludes ECR actions, Secrets Manager value reads, production names,
  and wildcard actions.
- Some AWS read APIs do not support resource-level permissions and therefore use `Resource: "*"`
  with a Region condition. This is not an `Action: "*"` grant.
- This is a starting least-privilege policy for the current source. Do not broaden it in response to
  an error until the denied action and resource have been captured and checked against the source.

## Placeholders

Render the JSON only outside the repository by replacing:

```text
<AWS_ACCOUNT_ID>
<AWS_REGION>
<ECR_PUBLISHER_USER_NAME>
<TERRAFORM_STATE_BUCKET>
<CRAWLER_STATE_BUCKET>
<VPC_ID>
<MAIN_DB_SECURITY_GROUP_ID>
```

Never put access keys, passwords, session tokens, secret payloads, or a database secret value in
these files. Keep rendered policies and `~/.aws/config` local; do not commit rendered physical
identifiers.

## Safe local rendering

Store the four physical inputs as User environment variables without committing them:

```powershell
[Environment]::SetEnvironmentVariable("INFORM_TFSTATE_BUCKET", "<terraform-state-bucket>", "User")
[Environment]::SetEnvironmentVariable("INFORM_CRAWLER_STATE_BUCKET", "<planned-crawler-state-bucket>", "User")
[Environment]::SetEnvironmentVariable("INFORM_VPC_ID", "<backend-instance-vpc-id>", "User")
[Environment]::SetEnvironmentVariable("INFORM_MAIN_DB_SG_ID", "<backend-instance-security-group-id>", "User")
```

Then render the three policies locally:

```powershell
& .\infra\aws\crawler\harness\iam\render-dev-policies.ps1
```

The renderer performs only `aws sts get-caller-identity`, validates all inputs, resolves the current
IAM publisher user, and writes JSON under the ignored `harness/iam/rendered/` directory. It contains
no IAM, S3, or EC2 mutation command and does not print any account or resource identifier.

## Console setup order

1. An administrator reviews and renders `terraform-dev-role-trust-policy.json` and
   `terraform-dev-role-permissions-policy.json` outside the repository.
2. Create the IAM role `inform-crawler-terraform-dev` with the rendered trust policy and attach the
   rendered permissions as one customer-managed or inline policy.
3. Attach the rendered `publisher-assume-role-policy.json` to the existing ECR publisher user.
4. Configure a local role profile without creating another access key:

   ```ini
   [profile inform-crawler-terraform-dev]
   role_arn = arn:aws:iam::<AWS_ACCOUNT_ID>:role/inform-crawler-terraform-dev
   source_profile = inform-crawler-dev
   region = <AWS_REGION>
   role_session_name = inform-crawler-terraform-dev
   ```

5. Verify the role profile with `aws sts get-caller-identity --profile
   inform-crawler-terraform-dev`. Do not paste or commit its output.

The pre-existing Terraform-state bucket must be created and hardened separately before remote
backend initialization. Do not run `terraform plan`, `terraform apply`, or the real dev harness as
part of this IAM setup unless each operation has been explicitly approved.
