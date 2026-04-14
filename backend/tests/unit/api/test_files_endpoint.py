"""Unit tests for the signed URL endpoint contract."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import files as files_endpoint
from app.schemas.file import FileDownloadURLResponse


async def test_get_file_url_returns_typed_response_without_storage_key(monkeypatch) -> None:
    owner_id = uuid.uuid4()
    file_id = uuid.uuid4()

    class FakeFileService:
        def __init__(self, db: object) -> None:
            self.db = db

        async def get_download_url_for_user(
            self, user_id: uuid.UUID, requested_file_id: uuid.UUID
        ) -> str | None:
            assert user_id == owner_id
            assert requested_file_id == file_id
            return "https://download.example.test/resume.pdf?signature=abc123"

    monkeypatch.setattr(files_endpoint, "FileService", FakeFileService)

    response = await files_endpoint.get_file_url(
        file_id=file_id,
        current_user=SimpleNamespace(id=owner_id),
        db=object(),
    )

    assert isinstance(response, FileDownloadURLResponse)
    assert response.model_dump() == {
        "url": "https://download.example.test/resume.pdf?signature=abc123"
    }
    assert "storage_key" not in response.model_dump()


async def test_get_file_url_returns_404_for_missing_file_id(monkeypatch) -> None:
    class FakeFileService:
        def __init__(self, db: object) -> None:
            self.db = db

        async def get_download_url_for_user(
            self, user_id: uuid.UUID, requested_file_id: uuid.UUID
        ) -> str | None:
            return None

    monkeypatch.setattr(files_endpoint, "FileService", FakeFileService)

    with pytest.raises(HTTPException) as exc_info:
        await files_endpoint.get_file_url(
            file_id=uuid.uuid4(),
            current_user=SimpleNamespace(id=uuid.uuid4()),
            db=object(),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "File not found."
