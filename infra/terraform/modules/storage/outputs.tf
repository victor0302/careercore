output "bucket_name" {
  description = "Name of the S3 resume-upload bucket"
  value       = aws_s3_bucket.resumes.bucket
}

output "bucket_arn" {
  description = "ARN of the S3 resume-upload bucket"
  value       = aws_s3_bucket.resumes.arn
}
