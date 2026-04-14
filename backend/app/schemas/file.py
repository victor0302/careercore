"""Pydantic schemas for file upload and signed-download responses."""

import uuid

from pydantic import BaseModel


class FileUploadResponse(BaseModel):
    id: uuid.UUID
    status: str
    filename: str


class FileDownloadURLResponse(BaseModel):
    url: str
