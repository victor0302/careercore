"""File extraction Celery tasks."""

import asyncio
import io
import uuid

from botocore.exceptions import BotoCoreError, ClientError
from docx import Document
from pypdf import PdfReader
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import AsyncSessionLocal
from app.models.uploaded_file import FileStatus, UploadedFile
from app.workers.celery_app import celery_app

_TRANSIENT_EXCEPTIONS = (BotoCoreError, ClientError, RuntimeError, SQLAlchemyError)


def _extract_text_from_bytes(content_type: str, data: bytes) -> str:
    if content_type == "application/pdf":
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(filter(None, (page.extract_text() or "" for page in reader.pages))).strip()

    if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        document = Document(io.BytesIO(data))
        return "\n".join(
            paragraph.text.strip()
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        )

    if content_type == "text/plain":
        return data.decode("utf-8")

    raise ValueError(f"Unsupported content type for extraction: {content_type}")


async def _set_file_error(
    file_id: uuid.UUID,
    message: str,
    session_factory=AsyncSessionLocal,
) -> None:
    async with session_factory() as session:
        record = await session.get(UploadedFile, file_id)
        if record is None:
            return
        record.status = FileStatus.error
        record.error_message = message
        await session.commit()


async def _extract_file_text_async(
    file_id: uuid.UUID,
    session_factory=AsyncSessionLocal,
    downloader=None,
    extractor=_extract_text_from_bytes,
) -> dict[str, object]:
    if downloader is None:
        from app.services.file_service import download_object_bytes

        downloader = download_object_bytes

    async with session_factory() as session:
        record = await session.get(UploadedFile, file_id)
        if record is None:
            return {"file_id": str(file_id), "status": "error", "chars_extracted": 0}

        record.status = FileStatus.processing
        record.error_message = None
        await session.commit()

        data = downloader(record.storage_key)
        extracted_text = extractor(record.content_type, data)

        record.extracted_text = extracted_text
        record.status = FileStatus.ready
        record.error_message = None
        await session.commit()

        return {
            "file_id": str(file_id),
            "status": "ready",
            "chars_extracted": len(extracted_text),
        }


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="default",
    name="app.workers.tasks.extraction_tasks.extract_file_text",
)
def extract_file_text(self: "celery_app.Task", file_id: str) -> dict:  # type: ignore[name-defined]
    """Extract text from an uploaded file and persist it to the database.

    Args:
        file_id: UUID string of the UploadedFile to process.

    Returns:
        {"file_id": str, "status": "ready" | "error", "chars_extracted": int}

    """
    parsed_file_id = uuid.UUID(file_id)
    try:
        return asyncio.run(_extract_file_text_async(parsed_file_id))
    except _TRANSIENT_EXCEPTIONS as exc:
        retries = getattr(self.request, "retries", 0)
        max_retries = getattr(self, "max_retries", 0)
        if retries < max_retries:
            raise self.retry(exc=exc)

        asyncio.run(_set_file_error(parsed_file_id, str(exc)))
        return {"file_id": file_id, "status": "error", "chars_extracted": 0}
    except Exception as exc:
        asyncio.run(_set_file_error(parsed_file_id, str(exc)))
        return {"file_id": file_id, "status": "error", "chars_extracted": 0}
