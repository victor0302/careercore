#!/usr/bin/env bash
# create_buckets.sh — Initialize MinIO bucket for local development.
# Requires mc (MinIO client) to be installed and the MinIO server to be running.

set -euo pipefail

MINIO_ALIAS="${MINIO_ALIAS:-local}"
MINIO_URL="${MINIO_URL:-http://localhost:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"
BUCKET="${MINIO_BUCKET:-careercore-uploads}"

echo "Configuring MinIO alias '${MINIO_ALIAS}' at ${MINIO_URL}..."
mc alias set "${MINIO_ALIAS}" "${MINIO_URL}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}"

echo "Creating bucket '${BUCKET}' (ignore-existing)..."
mc mb --ignore-existing "${MINIO_ALIAS}/${BUCKET}"

echo "Setting download policy on bucket..."
mc anonymous set download "${MINIO_ALIAS}/${BUCKET}"

echo "Done. Bucket '${BUCKET}' is ready."
