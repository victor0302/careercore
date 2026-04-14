"""Unit tests for the signed URL endpoint contract."""

import io
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.api.v1.endpoints import files as files_endpoint
from app.schemas.file import FileDownloadURLResponse, FileUploadResponse


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


async def test_get_file_url_returns_404_for_cross_user_access(monkeypatch) -> None:
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
            return None

    monkeypatch.setattr(files_endpoint, "FileService", FakeFileService)

    with pytest.raises(HTTPException) as exc_info:
        await files_endpoint.get_file_url(
            file_id=file_id,
            current_user=SimpleNamespace(id=owner_id),
            db=object(),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "File not found."


async def test_upload_file_maps_unsupported_type_to_415(monkeypatch) -> None:
    class FakeFileService:
        def __init__(self, db: object) -> None:
            self.db = db

        async def upload(
            self,
            *,
            user_id: uuid.UUID,
            filename: str,
            content_type: str,
            data: bytes,
        ) -> object:
            raise ValueError(
                "Unsupported file type: application/octet-stream. Allowed: PDF, DOCX, TXT."
            )

    monkeypatch.setattr(files_endpoint, "FileService", FakeFileService)

    upload = UploadFile(
        filename="resume.bin",
        file=io.BytesIO(b"binary"),
        headers={"content-type": "application/octet-stream"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await files_endpoint.upload_file(
            file=upload,
            current_user=SimpleNamespace(id=uuid.uuid4()),
            db=object(),
        )

    assert exc_info.value.status_code == 415


async def test_upload_file_maps_size_limit_to_413(monkeypatch) -> None:
    class FakeFileService:
        def __init__(self, db: object) -> None:
            self.db = db

        async def upload(
            self,
            *,
            user_id: uuid.UUID,
            filename: str,
            content_type: str,
            data: bytes,
        ) -> object:
            raise ValueError("File exceeds 10 MB limit.")

    monkeypatch.setattr(files_endpoint, "FileService", FakeFileService)

    upload = UploadFile(
        filename="resume.pdf",
        file=io.BytesIO(b"pdf"),
        headers={"content-type": "application/pdf"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await files_endpoint.upload_file(
            file=upload,
            current_user=SimpleNamespace(id=uuid.uuid4()),
            db=object(),
        )

    assert exc_info.value.status_code == 413


async def test_upload_file_returns_typed_response(monkeypatch) -> None:
    owner_id = uuid.uuid4()
    file_id = uuid.uuid4()

    class FakeFileService:
        def __init__(self, db: object) -> None:
            self.db = db

        async def upload(
            self,
            *,
            user_id: uuid.UUID,
            filename: str,
            content_type: str,
            data: bytes,
        ) -> object:
            assert user_id == owner_id
            assert filename == "resume.pdf"
            assert content_type == "application/pdf"
            assert data == b"pdf"
            return SimpleNamespace(
                id=file_id,
                status=SimpleNamespace(value="pending"),
                original_filename="resume.pdf",
            )

    monkeypatch.setattr(files_endpoint, "FileService", FakeFileService)

    upload = UploadFile(
        filename="resume.pdf",
        file=io.BytesIO(b"pdf"),
        headers={"content-type": "application/pdf"},
    )

    response = await files_endpoint.upload_file(
        file=upload,
        current_user=SimpleNamespace(id=owner_id),
        db=object(),
    )

    assert isinstance(response, FileUploadResponse)
    assert response.model_dump() == {
        "id": file_id,
        "status": "pending",
        "filename": "resume.pdf",
    }
