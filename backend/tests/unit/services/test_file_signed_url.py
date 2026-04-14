"""Unit tests for signed-download URL ownership and TTL behavior."""

import uuid
from types import SimpleNamespace

import pytest

from app.services.file_service import FileService, settings


def _make_service() -> FileService:
    service = object.__new__(FileService)
    service._db = object()
    service._s3 = SimpleNamespace()
    return service


async def test_get_download_url_for_user_returns_none_for_missing_or_non_owned_file() -> None:
    service = _make_service()

    async def fake_get_for_user(user_id: uuid.UUID, file_id: uuid.UUID) -> None:
        return None

    service.get_for_user = fake_get_for_user  # type: ignore[method-assign]
    service.get_presigned_url = lambda storage_key, expires_in=None: pytest.fail(  # type: ignore[method-assign]
        "presigned URL should not be generated for an inaccessible file"
    )

    result = await service.get_download_url_for_user(uuid.uuid4(), uuid.uuid4())

    assert result is None


async def test_get_download_url_for_user_uses_short_configured_ttl() -> None:
    service = _make_service()
    owner_id = uuid.uuid4()
    file_id = uuid.uuid4()
    captured: dict[str, object] = {}

    async def fake_get_for_user(user_id: uuid.UUID, requested_file_id: uuid.UUID) -> object:
        assert user_id == owner_id
        assert requested_file_id == file_id
        return SimpleNamespace(storage_key="internal/user-id/file-id/resume.pdf")

    def fake_get_presigned_url(storage_key: str, expires_in: int | None = None) -> str:
        captured["storage_key"] = storage_key
        captured["expires_in"] = expires_in
        return "https://download.example.test/resume.pdf?signature=abc123"

    service.get_for_user = fake_get_for_user  # type: ignore[method-assign]
    service.get_presigned_url = fake_get_presigned_url  # type: ignore[method-assign]

    url = await service.get_download_url_for_user(owner_id, file_id)

    assert url == "https://download.example.test/resume.pdf?signature=abc123"
    assert captured == {
        "storage_key": "internal/user-id/file-id/resume.pdf",
        "expires_in": None,
    }


def test_get_presigned_url_defaults_to_configured_short_ttl() -> None:
    service = _make_service()
    captured: dict[str, object] = {}

    def fake_generate_presigned_url(
        operation: str, *, Params: dict[str, str], ExpiresIn: int
    ) -> str:
        captured["operation"] = operation
        captured["params"] = Params
        captured["expires_in"] = ExpiresIn
        return "https://download.example.test/resume.pdf?signature=abc123"

    service._s3.generate_presigned_url = fake_generate_presigned_url  # type: ignore[attr-defined]

    url = service.get_presigned_url("internal/user-id/file-id/resume.pdf")

    assert url == "https://download.example.test/resume.pdf?signature=abc123"
    assert captured == {
        "operation": "get_object",
        "params": {
            "Bucket": settings.MINIO_BUCKET,
            "Key": "internal/user-id/file-id/resume.pdf",
        },
        "expires_in": settings.FILE_DOWNLOAD_URL_TTL_SECONDS,
    }
