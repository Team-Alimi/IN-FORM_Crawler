variable "environment" { type = string }

variable "schedule_enabled" {
  description = "Dev and prod schedules remain disabled until an approved apply enables them."
  type        = bool
  default     = false
}

variable "launch_template_id" { type = string }
variable "launch_template_arn" { type = string }
variable "launch_template_version" { type = string }
variable "subnet_ids" { type = list(string) }
variable "candidate_instance_types" { type = list(string) }
variable "worker_document_name" { type = string }
variable "worker_document_arn" { type = string }
variable "orchestration_role_arn" { type = string }
variable "orchestration_role_name" { type = string }
variable "scheduler_role_arn" { type = string }
variable "scheduler_role_name" { type = string }

variable "simulation" {
  description = "Dev-only failure injection passed to the worker command."
  type        = string
  default     = "NONE"
  validation {
    condition     = contains(["NONE", "BOOTSTRAP_TRANSIENT", "DB_CONNECTION_TRANSIENT", "S3_TRANSIENT", "SPOT_INTERRUPTION", "TIMEOUT"], var.simulation)
    error_message = "Unsupported worker simulation."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}
