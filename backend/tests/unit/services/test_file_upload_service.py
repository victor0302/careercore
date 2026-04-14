"""Unit tests for file upload validation, storage key generation, and queueing."""

import os
import uuid
from types import SimpleNamespace

import pytest

os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("MINIO_BUCKET", "careercore-test")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

from app.models.uploaded_file import FileStatus, UploadedFile
from app.services import file_service as file_service_module
from app.services.file_service import FileService, MAX_UPLOAD_BYTES


class _FakeDB:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushed = False

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed = True


def _make_service(db: _FakeDB, s3: object) -> FileService:
    service = object.__new__(FileService)
    service._db = db
    service._s3 = s3
    return service


async def test_upload_rejects_unsupported_mime_type() -> None:
    service = _make_service(_FakeDB(), SimpleNamespace())

    with pytest.raises(ValueError, match="Unsupported file type"):
        await service.upload(
            user_id=uuid.uuid4(),
            filename="resume.exe",
            content_type="application/octet-stream",
            data=b"x",
        )


async def test_upload_rejects_files_over_10_mb() -> None:
    service = _make_service(_FakeDB(), SimpleNamespace())

    with pytest.raises(ValueError, match="File exceeds 10 MB limit."):
        await service.upload(
            user_id=uuid.uuid4(),
            filename="resume.pdf",
            content_type="application/pdf",
            data=b"x" * (MAX_UPLOAD_BYTES + 1),
        )


async def test_upload_uses_opaque_storage_key_persists_pending_and_queues(monkeypatch) -> None:
    db = _FakeDB()
    captured: dict[str, object] = {}
    queued: list[str] = []
    created_records: list[object] = []

    class FakeUploadedFile:
        def __init__(self, **kwargs: object) -> None:
            created_records.append(self)
            for key, value in kwargs.items():
                setattr(self, key, value)

    def fake_put_object(*, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        captured["bucket"] = Bucket
        captured["key"] = Key
        captured["body"] = Body
        captured["content_type"] = ContentType

    monkeypatch.setattr(
        file_service_module.extract_file_text,
        "delay",
        lambda file_id: queued.append(file_id),
    )
    monkeypatch.setattr(file_service_module, "UploadedFile", FakeUploadedFile)

    user_id = uuid.uuid4()
    service = _make_service(db, SimpleNamespace(put_object=fake_put_object))

    record = await service.upload(
        user_id=user_id,
        filename="My Resume 2026.pdf",
        content_type="application/pdf",
        data=b"resume-bytes",
    )

    assert record is created_records[0]
    assert record.user_id == user_id
    assert record.original_filename == "My Resume 2026.pdf"
    assert record.status == FileStatus.pending
    assert record.size_bytes == len(b"resume-bytes")
    assert db.added == [record]
    assert db.flushed is True
    assert captured["bucket"] == file_service_module.settings.MINIO_BUCKET
    assert captured["body"] == b"resume-bytes"
    assert captured["content_type"] == "application/pdf"
    assert isinstance(captured["key"], str)
    assert "My Resume 2026.pdf" not in captured["key"]
    assert record.storage_key == captured["key"]
    assert record.storage_key.startswith(f"{user_id}/")
    assert record.storage_key.endswith(".pdf")
    assert queued == [str(record.id)]
