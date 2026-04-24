variable "app_name" {
  description = "Application name prefix for all resources"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID from the networking module"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs where ECS tasks run"
  type        = list(string)
}

variable "compute_security_group_id" {
  description = "Security group ID to attach to ECS tasks"
  type        = string
}

variable "backend_image" {
  description = "Docker image URI for the FastAPI backend (e.g., 123456789.dkr.ecr.us-east-1.amazonaws.com/careercore-backend:latest)"
  type        = string
}

variable "db_address" {
  description = "RDS hostname (without port) passed as DATABASE_URL host"
  type        = string
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "careercore"
}

variable "db_username" {
  description = "PostgreSQL master username"
  type        = string
  default     = "careercore"
}

variable "db_password" {
  description = "PostgreSQL master password"
  type        = string
  sensitive   = true
}

variable "s3_bucket_name" {
  description = "Name of the S3 bucket used for resume uploads"
  type        = string
}

variable "task_cpu" {
  description = "Fargate task CPU units (256 = 0.25 vCPU)"
  type        = string
  default     = "256"
}

variable "task_memory" {
  description = "Fargate task memory in MiB"
  type        = string
  default     = "512"
}

variable "desired_count" {
  description = "Number of backend task replicas to run"
  type        = number
  default     = 1
}
