output "backend_url" {
  description = "Public URL of the FastAPI backend"
  value       = "https://api.${var.app_name}.example.com"  # TODO: replace with actual resource output
}

output "frontend_url" {
  description = "Public URL of the Next.js frontend"
  value       = "https://${var.app_name}.example.com"  # TODO: replace with actual resource output
}

output "db_endpoint" {
  description = "PostgreSQL endpoint (internal)"
  value       = "db.${var.app_name}.internal"  # TODO: replace with RDS endpoint output
  sensitive   = true
}
