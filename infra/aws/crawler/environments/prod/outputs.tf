output "state_bucket_name" { value = module.state.bucket_name }
output "lock_table_name" { value = module.state.lock_table_name }
output "schedule_name" { value = module.scheduler.schedule_name }
output "state_machine_arn" { value = module.scheduler.state_machine_arn }
output "manual_execution_input" { value = module.scheduler.manual_execution_input }
