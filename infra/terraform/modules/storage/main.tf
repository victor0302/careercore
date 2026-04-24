# Storage module — Phase 1
# Provisions: S3 bucket for resume file uploads with versioning enabled
# and a bucket policy granting the ECS task role put/get access.

resource "aws_s3_bucket" "resumes" {
  bucket = var.bucket_name
  tags = {
    Name        = var.bucket_name
    Environment = var.environment
  }
}

resource "aws_s3_bucket_versioning" "resumes" {
  bucket = aws_s3_bucket.resumes.id
  versioning_configuration {
    status = "Enabled"
  }
}

data "aws_iam_policy_document" "bucket_policy" {
  statement {
    sid    = "AllowECSTaskAccess"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = [var.task_role_arn]
    }
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.resumes.arn}/*"]
  }
}

resource "aws_s3_bucket_policy" "resumes" {
  bucket = aws_s3_bucket.resumes.id
  policy = data.aws_iam_policy_document.bucket_policy.json
}
