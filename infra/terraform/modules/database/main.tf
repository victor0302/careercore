# Database module — Phase 1
# Provisions: RDS PostgreSQL 15 on db.t3.micro, placed in private subnets.
# The security group (created by the networking module) allows ingress from
# the compute tier only — no direct public access.

resource "aws_db_subnet_group" "main" {
  name       = "${var.app_name}-${var.environment}-db-subnet-group"
  subnet_ids = var.private_subnet_ids
  tags = { Name = "${var.app_name}-${var.environment}-db-subnet-group" }
}

resource "aws_db_instance" "postgres" {
  identifier             = "${var.app_name}-${var.environment}-postgres"
  engine                 = "postgres"
  engine_version         = "15"
  instance_class         = var.db_instance_class
  allocated_storage      = 20
  db_name                = var.db_name
  username               = var.db_username
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.db_security_group_id]
  publicly_accessible    = false
  storage_encrypted      = true
  backup_retention_period = 7
  skip_final_snapshot    = false
  deletion_protection    = true

  tags = { Name = "${var.app_name}-${var.environment}-postgres" }
}
