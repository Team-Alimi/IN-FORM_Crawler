variable "environment" { type = string }
variable "aws_region" { type = string }
variable "ami_id" { type = string }

variable "subnet_ids" {
  description = "At least two public subnets in distinct approved Availability Zones."
  type        = list(string)
  validation {
    condition     = length(var.subnet_ids) >= 2
    error_message = "At least two candidate subnets are required."
  }
}

variable "candidate_instance_types" {
  description = "At least two owner-approved x86_64 Playwright-compatible instance types."
  type        = list(string)
  validation {
    condition     = length(var.candidate_instance_types) >= 2
    error_message = "At least two x86_64 candidate instance types are required."
  }
}

variable "security_group_id" { type = string }
variable "runtime_instance_profile_name" { type = string }
variable "state_bucket_name" { type = string }
variable "state_prefix" { type = string }
variable "lock_table_name" { type = string }
variable "parameter_store_namespace" { type = string }
variable "database_secret_arn" { type = string }

variable "crawler_image_ref" {
  description = "Immutable crawler image reference. Publication is handled separately."
  type        = string
  validation {
    condition     = can(regex("@sha256:[0-9a-fA-F]{64}$", var.crawler_image_ref))
    error_message = "crawler_image_ref must end with an immutable sha256 digest."
  }
}

variable "crawler_git_sha" {
  description = "Git commit represented by crawler_image_ref."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-fA-F]{40}([0-9a-fA-F]{24})?$", var.crawler_git_sha))
    error_message = "crawler_git_sha must be a 40- or 64-character hexadecimal commit ID."
  }
}

variable "root_volume_size_gib" {
  type    = number
  default = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}
