output "ecs_cluster_id" {
  description = "ARN of the ECS cluster"
  value       = aws_ecs_cluster.main.id
}

output "ecs_service_name" {
  description = "Name of the backend ECS service"
  value       = aws_ecs_service.backend.name
}

output "task_role_arn" {
  description = "ARN of the IAM role assumed by running ECS tasks (used for S3 bucket policy)"
  value       = aws_iam_role.task.arn
}
