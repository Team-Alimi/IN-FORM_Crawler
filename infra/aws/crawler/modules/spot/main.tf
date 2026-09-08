locals {
  allocation_strategy = "price-capacity-optimized"
  tags = merge(var.tags, {
    Application = "inform-crawler"
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

resource "aws_launch_template" "worker" {
  name_prefix   = "inform-crawler-${var.environment}-"
  image_id      = var.ami_id
  instance_type = var.candidate_instance_types[0]
  user_data = base64encode(templatefile("${path.module}/user-data.sh.tftpl", {
    environment = var.environment
  }))

  instance_initiated_shutdown_behavior = "terminate"
  update_default_version               = true

  iam_instance_profile { name = var.runtime_instance_profile_name }

  network_interfaces {
    associate_public_ip_address = true
    delete_on_termination       = true
    device_index                = 0
    security_groups             = [var.security_group_id]
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
    instance_metadata_tags      = "enabled"
  }

  instance_market_options {
    market_type = "spot"
    spot_options { instance_interruption_behavior = "terminate" }
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      delete_on_termination = true
      encrypted             = true
      volume_size           = var.root_volume_size_gib
      volume_type           = "gp3"
    }
  }

  tag_specifications {
    resource_type = "instance"
    tags          = merge(local.tags, { Name = "inform-crawler-${var.environment}" })
  }

  tag_specifications {
    resource_type = "volume"
    tags          = local.tags
  }

  tags = local.tags

  lifecycle { create_before_destroy = true }
}

resource "aws_ssm_document" "worker" {
  name            = "inform-crawler-worker-${var.environment}"
  document_type   = "Command"
  document_format = "JSON"
  target_type     = "/AWS::EC2::Instance"
  tags            = local.tags

  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Run one contract-bound IN-FORM ephemeral crawler attempt"
    parameters = {
      RunUuid = {
        type           = "String"
        allowedPattern = "^[0-9a-fA-F-]{36}$"
      }
      Simulation = {
        type          = "String"
        default       = "NONE"
        allowedValues = ["NONE", "BOOTSTRAP_TRANSIENT", "DB_CONNECTION_TRANSIENT", "S3_TRANSIENT", "SPOT_INTERRUPTION", "TIMEOUT"]
      }
    }
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "runCrawlerAttempt"
      inputs = {
        timeoutSeconds = "7500"
        runCommand = [templatefile("${path.module}/worker-command.sh.tftpl", {
          crawler_git_sha          = var.crawler_git_sha
          crawler_image_ref        = var.crawler_image_ref
          database_secret_arn      = var.database_secret_arn
          lock_table_name          = var.lock_table_name
          parameter_namespace      = trimsuffix(var.parameter_store_namespace, "/")
          state_bucket_name        = var.state_bucket_name
          state_prefix             = var.state_prefix
        })]
      }
    }]
  })
}
