variable "app_name" {
  description = "Application name prefix for all resources"
  type        = string
}

variable "environment" {
  description = "Deployment environment (development, staging, production)"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Two availability zones used for subnet placement"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}
