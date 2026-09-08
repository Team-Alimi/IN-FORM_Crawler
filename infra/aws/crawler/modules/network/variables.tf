variable "environment" { type = string }
variable "vpc_id" { type = string }

variable "crawler_security_group_id" {
  description = "Existing crawler SG ID, or null to create the contract SG."
  type        = string
  default     = null
  nullable    = true
}

variable "main_db_security_group_id" {
  description = "Main PostgreSQL SG receiving only crawler SG TCP 5432."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
