locals {
  tags = merge(var.tags, {
    Application = "inform-crawler"
    Environment = var.environment
    ManagedBy   = "terraform"
  })
  fleet_overrides = flatten([
    for subnet_id in var.subnet_ids : [
      for instance_type in var.candidate_instance_types : {
        SubnetId     = subnet_id
        InstanceType = instance_type
      }
    ]
  ])
  subnet_arns = [
    for subnet_id in var.subnet_ids :
    "arn:${data.aws_partition.current.partition}:ec2:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:subnet/${subnet_id}"
  ]
}

data "aws_iam_policy_document" "orchestration" {
  statement {
    sid       = "LaunchOnlyApprovedWorkerTemplate"
    actions   = ["ec2:CreateFleet", "ec2:RunInstances"]
    resources = ["*"]
    condition {
      test     = "ArnEquals"
      variable = "ec2:LaunchTemplate"
      values   = [var.launch_template_arn]
    }
    condition {
      test     = "ArnEquals"
      variable = "ec2:Subnet"
      values   = local.subnet_arns
    }
    condition {
      test     = "StringEquals"
      variable = "ec2:InstanceType"
      values   = var.candidate_instance_types
    }
  }

  statement {
    sid = "ObserveAndTerminateApprovedExecution"
    actions = [
      "ec2:CreateTags",
      "ec2:DescribeFleetInstances",
      "ec2:DescribeFleets",
      "ec2:DescribeInstances",
      "ec2:TerminateInstances",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [data.aws_region.current.name]
    }
  }

  statement {
    sid       = "RunApprovedWorkerDocument"
    actions   = ["ssm:SendCommand"]
    resources = [var.worker_document_arn, "arn:${data.aws_partition.current.partition}:ec2:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:instance/*"]
  }

  statement {
    sid       = "ObserveWorkerCommand"
    actions   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"]
    resources = ["*"]
  }
}

data "aws_partition" "current" {}
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

resource "aws_iam_role_policy" "orchestration" {
  name   = "inform-crawler-orchestration-${var.environment}"
  role   = var.orchestration_role_name
  policy = data.aws_iam_policy_document.orchestration.json
}

resource "aws_sfn_state_machine" "crawler" {
  name       = "inform-crawler-orchestration-${var.environment}"
  role_arn   = var.orchestration_role_arn
  type       = "STANDARD"
  definition = file("${path.module}/state-machine.asl.json")
  tags       = local.tags
}

data "aws_iam_policy_document" "scheduler_start" {
  statement {
    sid       = "StartOnlyCrawlerOrchestration"
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.crawler.arn]
  }
}

resource "aws_iam_role_policy" "scheduler_start" {
  name   = "inform-crawler-start-orchestration-${var.environment}"
  role   = var.scheduler_role_name
  policy = data.aws_iam_policy_document.scheduler_start.json
}

resource "aws_scheduler_schedule" "daily" {
  name                         = "inform-crawler-scheduler-${var.environment}"
  description                  = "Daily ephemeral IN-FORM crawler trigger"
  schedule_expression          = "cron(0 6 * * ? *)"
  schedule_expression_timezone = "Asia/Seoul"
  state                        = var.schedule_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window { mode = "OFF" }

  target {
    arn      = aws_sfn_state_machine.crawler.arn
    role_arn = var.scheduler_role_arn
    input = jsonencode({
      Attempt               = 1
      LaunchTemplateId      = var.launch_template_id
      LaunchTemplateVersion = tostring(var.launch_template_version)
      Overrides             = local.fleet_overrides
      WorkerDocumentName    = var.worker_document_name
      Simulation            = var.simulation
    })

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 0
    }
  }
}
