variable "region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "app_name" {
  description = "Application name used as a prefix for all resources"
  type        = string
  default     = "careercore"
}

variable "environment" {
  description = "Deployment environment (development, staging, production)"
  type        = string
  default     = "development"
}

variable "db_password" {
  description = "PostgreSQL master password — store in SSM or Vault, never in tfvars"
  type        = string
  sensitive   = true
}
