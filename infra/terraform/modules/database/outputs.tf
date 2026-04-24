output "db_address" {
  description = "RDS hostname (without port) for use in connection strings"
  value       = aws_db_instance.postgres.address
}

output "db_endpoint" {
  description = "RDS connection endpoint in address:port format"
  value       = aws_db_instance.postgres.endpoint
  sensitive   = true
}

output "db_port" {
  description = "RDS listener port"
  value       = aws_db_instance.postgres.port
}

output "db_name" {
  description = "Name of the initial PostgreSQL database"
  value       = aws_db_instance.postgres.db_name
}
