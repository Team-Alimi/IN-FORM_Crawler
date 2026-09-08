variable "environment" {
  description = "Deployment environment, limited to dev or prod."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod."
  }
}

variable "bucket_name" {
  description = "Globally unique physical crawler-state bucket name."
  type        = string
}

variable "state_prefix" {
  description = "Optional prefix within the dedicated crawler-state bucket."
  type        = string
  default     = ""
}

variable "lock_table_name" {
  description = "Physical DynamoDB runtime-lock table name."
  type        = string
}

variable "tags" {
  description = "Additional non-sensitive resource tags."
  type        = map(string)
  default     = {}
}
