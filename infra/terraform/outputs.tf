output "backend_url" {
  description = "ECS service identifier for the FastAPI backend (Phase 1: no public ALB; add load balancer in Phase 2 for an HTTPS URL)"
  value       = "ecs://${module.compute.ecs_cluster_id}/${module.compute.ecs_service_name}"
}

output "frontend_url" {
  description = "Frontend deployment target (Phase 1: not provisioned; wire CloudFront + S3 static site in Phase 2)"
  value       = "${var.app_name}-${var.environment}-frontend"
}

output "db_endpoint" {
  description = "PostgreSQL RDS endpoint in address:port format (internal use only)"
  value       = module.database.db_endpoint
  sensitive   = true
}
