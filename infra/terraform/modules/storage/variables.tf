variable "app_name" {
  description = "Application name prefix for all resources"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "bucket_name" {
  description = "Globally unique S3 bucket name for resume uploads"
  type        = string
}

variable "task_role_arn" {
  description = "ARN of the ECS task IAM role — granted GetObject and PutObject on the bucket"
  type        = string
}
