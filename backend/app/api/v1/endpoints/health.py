"""Health check endpoint — no authentication required."""

import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Return the operational status of all dependent services.

    Response:
      200 — all services healthy: {"status": "ok", "version": "x.y.z", ...}
      503 — one or more services degraded: {"status": "degraded", ...}
    """
    db_status = "connected"
    redis_status = "connected"
    storage_status = "connected"

    # Check database
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("Health check — DB error: %s", exc)
        db_status = "error"

    # Check Redis
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
    except Exception as exc:
        logger.error("Health check — Redis error: %s", exc)
        redis_status = "error"

    # Check MinIO (boto3 is sync — do a quick head_bucket)
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        s3 = boto3.client(
            "s3",
            endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
        )
        s3.head_bucket(Bucket=settings.MINIO_BUCKET)
    except Exception as exc:
        logger.error("Health check — storage error: %s", exc)
        storage_status = "error"

    all_ok = all(s == "connected" for s in [db_status, redis_status, storage_status])
    status_code = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if all_ok else "degraded",
            "version": settings.APP_VERSION,
            "db": db_status,
            "redis": redis_status,
            "storage": storage_status,
        },
    )
