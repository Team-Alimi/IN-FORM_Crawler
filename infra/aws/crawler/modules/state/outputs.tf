output "bucket_name" { value = aws_s3_bucket.state.id }
output "bucket_arn" { value = aws_s3_bucket.state.arn }
output "state_prefix" { value = local.key_prefix }
output "lock_table_name" { value = aws_dynamodb_table.runtime_lock.name }
output "lock_table_arn" { value = aws_dynamodb_table.runtime_lock.arn }
