output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs of the two public subnets"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of the two private subnets"
  value       = aws_subnet.private[*].id
}

output "compute_security_group_id" {
  description = "Security group ID assigned to ECS Fargate tasks"
  value       = aws_security_group.compute.id
}

output "db_security_group_id" {
  description = "Security group ID assigned to the RDS instance"
  value       = aws_security_group.database.id
}
