output "schedule_name" { value = aws_scheduler_schedule.daily.name }
output "state_machine_arn" { value = aws_sfn_state_machine.crawler.arn }
output "manual_execution_input" {
  value = jsonencode({
    Attempt               = 1
    LaunchTemplateId      = var.launch_template_id
    LaunchTemplateVersion = tostring(var.launch_template_version)
    Overrides             = local.fleet_overrides
    WorkerDocumentName    = var.worker_document_name
    Simulation            = var.simulation
  })
}
