locals {
  normalized_prefix = trim(var.state_prefix, "/")
  key_prefix        = local.normalized_prefix == "" ? "" : "${local.normalized_prefix}/"
  tags = merge(var.tags, {
    Application = "inform-crawler"
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

resource "aws_s3_bucket" "state" {
  bucket        = var.bucket_name
  force_destroy = false
  tags          = local.tags
}

resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id
  rule { object_ownership = "BucketOwnerEnforced" }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

data "aws_iam_policy_document" "https_only" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/*",
    ]
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "https_only" {
  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.https_only.json
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket     = aws_s3_bucket.state.id
  depends_on = [aws_s3_bucket_versioning.state]

  rule {
    id     = "history-runs-90-days"
    status = "Enabled"
    filter { prefix = "${local.key_prefix}history/runs/" }
    expiration { days = 90 }
    noncurrent_version_expiration { noncurrent_days = 90 }
  }

  rule {
    id     = "success-logs-30-days"
    status = "Enabled"
    filter { prefix = "${local.key_prefix}logs/" }
    expiration { days = 30 }
    noncurrent_version_expiration { noncurrent_days = 30 }
  }

  rule {
    id     = "failure-artifacts-90-days"
    status = "Enabled"
    filter { prefix = "${local.key_prefix}failures/" }
    expiration { days = 90 }
    noncurrent_version_expiration { noncurrent_days = 90 }
  }

  rule {
    id     = "abort-failure-multipart-uploads-7-days"
    status = "Enabled"
    filter { prefix = "${local.key_prefix}failures/" }
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }

  rule {
    id     = "failure-queue-30-days"
    status = "Enabled"
    filter {
      and {
        prefix = "${local.key_prefix}failures/"
        tags   = { ArtifactClass = "queue" }
      }
    }
    expiration { days = 30 }
    noncurrent_version_expiration { noncurrent_days = 30 }
  }
}

resource "aws_dynamodb_table" "runtime_lock" {
  name         = var.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "lock_key"

  attribute {
    name = "lock_key"
    type = "S"
  }

  server_side_encryption { enabled = true }
  tags = local.tags
}
