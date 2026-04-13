"""File extraction Celery tasks.

These tasks run asynchronously after a file is uploaded.

Full implementation steps for extract_file_text:
  1. Load the UploadedFile record from the database (use a sync DB session for Celery).
  2. Download the file bytes from MinIO using boto3.
  3. Extract text:
     - PDF: use pypdf.PdfReader.
     - DOCX: use python-docx Document.
     - TXT: decode as UTF-8.
  4. Save the extracted text to UploadedFile.extracted_text.
  5. Set UploadedFile.status = FileStatus.ready.
  6. Commit the transaction.
  7. On failure (after all retries), set status = FileStatus.error and save error_message.
"""

import uuid

from app.workers.celery_app import celery_app


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

    TODO: Implement the extraction logic described in the module docstring.
    Retry on transient MinIO/DB errors using self.retry(exc=exc).
    """
    # Stub — not yet implemented
    return {"file_id": file_id, "status": "not_implemented", "chars_extracted": 0}
