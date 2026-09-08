data "aws_partition" "current" {}
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  tags = merge(var.tags, {
    Application = "inform-crawler"
    Environment = var.environment
    ManagedBy   = "terraform"
  })
  parameter_arn = "arn:${data.aws_partition.current.partition}:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${trimsuffix(var.parameter_store_namespace, "/")}/*"
}

data "aws_iam_policy_document" "runtime_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "runtime" {
  name               = "inform-crawler-runtime-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.runtime_assume.json
  tags               = local.tags
}

resource "aws_iam_instance_profile" "runtime" {
  name = "inform-crawler-runtime-profile-${var.environment}"
  role = aws_iam_role.runtime.name
  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "runtime_ssm_core" {
  role       = aws_iam_role.runtime.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "runtime" {
  statement {
    sid       = "ListCrawlerState"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [var.state_bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["history/*", "logs/*", "failures/*", "*/history/*", "*/logs/*", "*/failures/*"]
    }
  }

  statement {
    sid = "ReadWriteCrawlerStateObjects"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:PutObjectTagging",
      "s3:AbortMultipartUpload",
    ]
    resources = ["${var.state_bucket_arn}/*"]
  }

  statement {
    sid = "OwnRuntimeLease"
    actions = [
      "dynamodb:DeleteItem",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
    ]
    resources = [var.lock_table_arn]
  }

  statement {
    sid       = "ReadRuntimeParameters"
    actions   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
    resources = [local.parameter_arn]
  }

  statement {
    sid       = "ReadApprovedDatabaseSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.database_secret_arn]
  }
}

resource "aws_iam_role_policy" "runtime" {
  name   = "inform-crawler-runtime-${var.environment}"
  role   = aws_iam_role.runtime.id
  policy = data.aws_iam_policy_document.runtime.json
}

data "aws_iam_policy_document" "orchestration_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "orchestration" {
  name               = "inform-crawler-orchestration-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.orchestration_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "orchestration_pass_runtime_role" {
  statement {
    sid       = "PassOnlyCrawlerRuntimeRole"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.runtime.arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "orchestration_pass_runtime_role" {
  name   = "inform-crawler-pass-runtime-${var.environment}"
  role   = aws_iam_role.orchestration.id
  policy = data.aws_iam_policy_document.orchestration_pass_runtime_role.json
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "inform-crawler-scheduler-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
  tags               = local.tags
}
