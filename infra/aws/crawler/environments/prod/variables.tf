variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "vpc_id" { type = string }

variable "subnet_ids" {
  description = "At least two approved public subnets in distinct AZs."
  type        = list(string)
  validation {
    condition     = length(var.subnet_ids) >= 2
    error_message = "At least two subnets are required."
  }
}

variable "crawler_security_group_id" {
  type     = string
  default  = null
  nullable = true
}

variable "main_db_security_group_id" { type = string }

variable "candidate_instance_types" {
  description = "At least two approved x86_64 Playwright-compatible types."
  type        = list(string)
  validation {
    condition     = length(var.candidate_instance_types) >= 2
    error_message = "At least two candidate instance types are required."
  }
}

variable "state_bucket_name" { type = string }
variable "state_prefix" {
  type    = string
  default = ""
}

variable "parameter_store_namespace" { type = string }
variable "database_secret_arn" { type = string }
variable "ami_id" { type = string }

variable "crawler_image_ref" {
  type = string
  validation {
    condition     = can(regex("@sha256:[0-9a-fA-F]{64}$", var.crawler_image_ref))
    error_message = "Use an immutable image digest."
  }
}

variable "crawler_git_sha" {
  type = string
  validation {
    condition     = can(regex("^[0-9a-fA-F]{40}([0-9a-fA-F]{24})?$", var.crawler_git_sha))
    error_message = "Use the commit represented by crawler_image_ref."
  }
}

variable "schedule_enabled" {
  type    = bool
  default = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
