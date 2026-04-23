# Compute module — Phase 1
# Provisions: ECS Fargate cluster, IAM roles, task definition, and service
# for the FastAPI backend. No load balancer in Phase 1; add ALB in Phase 2.

data "aws_region" "current" {}

resource "aws_ecs_cluster" "main" {
  name = "${var.app_name}-${var.environment}"
  tags = { Name = "${var.app_name}-${var.environment}-cluster" }
}

data "aws_iam_policy_document" "ecs_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role — allows ECS to pull images and write CloudWatch logs
resource "aws_iam_role" "execution" {
  name               = "${var.app_name}-${var.environment}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Task role — assumed by the running container (S3 access)
resource "aws_iam_role" "task" {
  name               = "${var.app_name}-${var.environment}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_iam_role_policy" "task_s3" {
  name = "s3-resume-access"
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject"]
      Resource = "arn:aws:s3:::${var.s3_bucket_name}/*"
    }]
  })
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${var.app_name}-${var.environment}/backend"
  retention_in_days = 14
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.app_name}-${var.environment}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  # Phase 1: DB credentials passed as env vars. Use Secrets Manager in production.
  container_definitions = jsonencode([{
    name      = "backend"
    image     = var.backend_image
    essential = true
    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]
    environment = [
      { name = "DATABASE_URL", value = "postgresql://${var.db_username}:${var.db_password}@${var.db_address}:5432/${var.db_name}" },
      { name = "S3_BUCKET",    value = var.s3_bucket_name },
      { name = "ENVIRONMENT",  value = var.environment }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.backend.name
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = "backend"
      }
    }
  }])
}

resource "aws_ecs_service" "backend" {
  name            = "${var.app_name}-${var.environment}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [var.compute_security_group_id]
  }

  lifecycle {
    ignore_changes = [task_definition]
  }
}
