variable "environment" { type = string }
variable "state_bucket_arn" { type = string }
variable "lock_table_arn" { type = string }
variable "database_secret_arn" { type = string }

variable "parameter_store_namespace" {
  description = "Absolute SSM Parameter Store path, for example /inform/crawler/dev."
  type        = string

  validation {
    condition     = startswith(var.parameter_store_namespace, "/")
    error_message = "parameter_store_namespace must start with /."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}
