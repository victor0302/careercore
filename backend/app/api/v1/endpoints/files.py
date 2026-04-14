"""File upload and retrieval endpoints."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.file import FileDownloadURLResponse, FileUploadResponse
from app.services.file_service import FileService

router = APIRouter()

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileUploadResponse:
    """Upload a resume or supporting document (PDF, DOCX, TXT, max 10 MB)."""
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, DOCX, TXT.",
        )
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 10 MB limit.",
        )
    service = FileService(db)
    record = await service.upload(
        user_id=current_user.id,
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        data=data,
    )
    return FileUploadResponse(
        id=record.id,
        status=record.status.value,
        filename=record.original_filename,
    )


@router.get("/{file_id}/url", response_model=FileDownloadURLResponse)
async def get_file_url(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileDownloadURLResponse:
    """Return a short-lived presigned download URL for a file. Enforces ownership."""
    service = FileService(db)
    url = await service.get_download_url_for_user(current_user.id, file_id)
    if url is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    return FileDownloadURLResponse(url=url)
