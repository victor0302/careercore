# CareerCore — Phase 1 AWS infrastructure
#
# Deployment target : AWS (us-east-1 default; override via var.region)
# Support boundary  : Phase 1 / dev environment
#                     Single-AZ-resilient layout, no NAT Gateway, no ALB.
#                     Phase 2 additions: ALB, NAT Gateway, WAF, CDN, Secrets Manager.
#
# Module dependency order (no circular deps):
#   networking → database, compute
#   compute    → storage (task_role_arn)

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.6.0"
}

provider "aws" {
  region = var.region
}

locals {
  # Bucket name is derived here so both compute and storage modules share the same value
  # without creating a circular module dependency.
  bucket_name = "${var.app_name}-${var.environment}-resumes"
}

module "networking" {
  source             = "./modules/networking"
  app_name           = var.app_name
  environment        = var.environment
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
}

module "database" {
  source               = "./modules/database"
  app_name             = var.app_name
  environment          = var.environment
  private_subnet_ids   = module.networking.private_subnet_ids
  db_security_group_id = module.networking.db_security_group_id
  db_password          = var.db_password
  db_name              = var.db_name
  db_username          = var.db_username
}

module "compute" {
  source                    = "./modules/compute"
  app_name                  = var.app_name
  environment               = var.environment
  vpc_id                    = module.networking.vpc_id
  private_subnet_ids        = module.networking.private_subnet_ids
  compute_security_group_id = module.networking.compute_security_group_id
  backend_image             = var.backend_image
  db_address                = module.database.db_address
  db_name                   = var.db_name
  db_username               = var.db_username
  db_password               = var.db_password
  s3_bucket_name            = local.bucket_name
  task_cpu                  = var.task_cpu
  task_memory               = var.task_memory
  desired_count             = var.desired_count
}

module "storage" {
  source        = "./modules/storage"
  app_name      = var.app_name
  environment   = var.environment
  bucket_name   = local.bucket_name
  task_role_arn = module.compute.task_role_arn
}
