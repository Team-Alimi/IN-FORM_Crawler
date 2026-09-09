locals {
  environment     = "dev"
  lock_table_name = "inform-crawler-runtime-lock-dev"
}

module "state" {
  source = "../../modules/state"

  environment     = local.environment
  bucket_name     = var.state_bucket_name
  state_prefix    = var.state_prefix
  lock_table_name = local.lock_table_name
  tags            = var.tags
}

module "network" {
  source = "../../modules/network"

  environment               = local.environment
  vpc_id                    = var.vpc_id
  crawler_security_group_id = var.crawler_security_group_id
  main_db_security_group_id = var.main_db_security_group_id
  tags                      = var.tags
}

module "iam" {
  source = "../../modules/iam"

  environment                = local.environment
  state_bucket_arn           = module.state.bucket_arn
  lock_table_arn             = module.state.lock_table_arn
  database_secret_arn        = var.database_secret_arn
  crawler_ecr_repository_arn = var.crawler_ecr_repository_arn
  parameter_store_namespace  = var.parameter_store_namespace
  tags                       = var.tags
}

module "spot" {
  source = "../../modules/spot"

  environment                   = local.environment
  aws_region                    = var.region
  ami_id                        = var.ami_id
  subnet_ids                    = var.subnet_ids
  candidate_instance_types      = var.candidate_instance_types
  security_group_id             = module.network.crawler_security_group_id
  runtime_instance_profile_name = module.iam.runtime_instance_profile_name
  state_bucket_name             = module.state.bucket_name
  state_prefix                  = module.state.state_prefix
  lock_table_name               = module.state.lock_table_name
  parameter_store_namespace     = var.parameter_store_namespace
  database_secret_arn           = var.database_secret_arn
  crawler_image_ref             = var.crawler_image_ref
  crawler_git_sha               = var.crawler_git_sha
  tags                          = var.tags
}
module "scheduler" {
  source = "../../modules/scheduler"

  environment              = local.environment
  schedule_enabled         = var.schedule_enabled
  launch_template_id       = module.spot.launch_template_id
  launch_template_arn      = module.spot.launch_template_arn
  launch_template_version  = tostring(module.spot.launch_template_version)
  subnet_ids               = module.spot.subnet_ids
  candidate_instance_types = module.spot.candidate_instance_types
  worker_document_name     = module.spot.worker_document_name
  worker_document_arn      = module.spot.worker_document_arn
  orchestration_role_arn   = module.iam.orchestration_role_arn
  orchestration_role_name  = module.iam.orchestration_role_name
  scheduler_role_arn       = module.iam.scheduler_role_arn
  scheduler_role_name      = module.iam.scheduler_role_name
  tags                     = var.tags
}
