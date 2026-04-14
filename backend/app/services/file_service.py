"""File service — upload, retrieve, and delete files via MinIO."""

import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.uploaded_file import FileStatus, UploadedFile

settings = get_settings()


def _get_s3_client() -> "boto3.client":  # type: ignore[name-defined]
    return boto3.client(
        "s3",
        endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
    )


class FileService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._s3 = _get_s3_client()

    async def upload(
        self,
        user_id: uuid.UUID,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> UploadedFile:
        """Upload a file to MinIO and create an UploadedFile record.

        Steps:
          1. Generate a unique storage key (user_id/file_id/filename).
          2. Upload bytes to MinIO.
          3. Persist UploadedFile with status=pending.
          4. Enqueue extraction_tasks.extract_file_text.delay(file_id).

        TODO: Enqueue the Celery extraction task in step 4.
        """
        file_id = uuid.uuid4()
        storage_key = f"{user_id}/{file_id}/{filename}"

        try:
            self._s3.put_object(
                Bucket=settings.MINIO_BUCKET,
                Key=storage_key,
                Body=data,
                ContentType=content_type,
            )
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError(f"Failed to upload to MinIO: {exc}") from exc

        record = UploadedFile(
            id=file_id,
            user_id=user_id,
            original_filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            storage_key=storage_key,
            status=FileStatus.pending,
        )
        self._db.add(record)
        await self._db.flush()
        return record

    async def get_for_user(self, user_id: uuid.UUID, file_id: uuid.UUID) -> UploadedFile | None:
        """Return an UploadedFile only if it belongs to user_id."""
        result = await self._db.execute(
            select(UploadedFile).where(
                UploadedFile.id == file_id,
                UploadedFile.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_download_url_for_user(self, user_id: uuid.UUID, file_id: uuid.UUID) -> str | None:
        """Return a short-lived presigned download URL only for the file owner."""
        record = await self.get_for_user(user_id, file_id)
        if record is None:
            return None
        return self.get_presigned_url(record.storage_key)

    def get_presigned_url(self, storage_key: str, expires_in: int | None = None) -> str:
        """Generate a presigned GET URL for a file in MinIO."""
        ttl = expires_in or settings.FILE_DOWNLOAD_URL_TTL_SECONDS
        return self._s3.generate_presigned_url(  # type: ignore[no-any-return]
            "get_object",
            Params={"Bucket": settings.MINIO_BUCKET, "Key": storage_key},
            ExpiresIn=ttl,
        )
