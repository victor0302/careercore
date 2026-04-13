# Phase 1 IaC — configure for your cloud provider
# This stub provisions the top-level AWS provider.
# See modules/ for networking, compute, database, and storage sub-modules.

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

# Uncomment and configure modules as needed:
# module "networking" {
#   source   = "./modules/networking"
#   app_name = var.app_name
# }

# module "database" {
#   source      = "./modules/database"
#   app_name    = var.app_name
#   db_password = var.db_password
# }

# module "compute" {
#   source   = "./modules/compute"
#   app_name = var.app_name
# }

# module "storage" {
#   source   = "./modules/storage"
#   app_name = var.app_name
# }
