output "launch_template_id" { value = aws_launch_template.worker.id }
output "launch_template_arn" { value = aws_launch_template.worker.arn }
output "launch_template_version" { value = aws_launch_template.worker.latest_version }
output "worker_document_name" { value = aws_ssm_document.worker.name }
output "worker_document_arn" { value = aws_ssm_document.worker.arn }
output "subnet_ids" { value = var.subnet_ids }
output "candidate_instance_types" { value = var.candidate_instance_types }
