import uuid

from app.core.security import hash_password
from app.models.uploaded_file import FileStatus, UploadedFile
from app.models.user import User
from app.services import file_service as file_service_module
from app.services.file_service import FileService


async def _login(client, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


async def test_get_file_url_returns_owner_url_without_storage_key(
    client, mock_user, db, monkeypatch
) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    file_id = uuid.uuid4()
    record = UploadedFile(
        id=file_id,
        user_id=mock_user.id,
        original_filename="resume.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        storage_key=f"{mock_user.id}/{file_id}.pdf",
        status=FileStatus.ready,
    )
    db.add(record)
    await db.flush()

    def fake_get_presigned_url(
        self, storage_key: str, expires_in: int | None = None
    ) -> str:
        assert isinstance(self, FileService)
        assert storage_key == record.storage_key
        ttl = expires_in or file_service_module.settings.FILE_DOWNLOAD_URL_TTL_SECONDS
        assert ttl == file_service_module.settings.FILE_DOWNLOAD_URL_TTL_SECONDS
        return f"https://download.example.test/{file_id}.pdf?ttl={ttl}"

    monkeypatch.setattr(FileService, "get_presigned_url", fake_get_presigned_url)

    response = await client.get(f"/api/v1/files/{file_id}/url", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "url": f"https://download.example.test/{file_id}.pdf?ttl=300"
    }
    assert "storage_key" not in response.json()


async def test_get_file_url_returns_404_for_cross_user_access(
    client, mock_user, db, monkeypatch
) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    other_user = User(
        id=uuid.uuid4(),
        email="other-file-owner@careercore.test",
        password_hash=hash_password("Otherpassword123"),
        is_active=True,
    )
    db.add(other_user)
    await db.flush()

    foreign_file_id = uuid.uuid4()
    foreign_record = UploadedFile(
        id=foreign_file_id,
        user_id=other_user.id,
        original_filename="foreign.pdf",
        content_type="application/pdf",
        size_bytes=4096,
        storage_key=f"{other_user.id}/{foreign_file_id}.pdf",
        status=FileStatus.ready,
    )
    db.add(foreign_record)
    await db.flush()

    def fake_get_presigned_url(
        self, storage_key: str, expires_in: int | None = None
    ) -> str:
        raise AssertionError("Cross-user access should not reach presigned URL generation")

    monkeypatch.setattr(FileService, "get_presigned_url", fake_get_presigned_url)

    response = await client.get(f"/api/v1/files/{foreign_file_id}/url", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "File not found."


async def test_get_file_url_returns_404_for_missing_file_id(
    client, mock_user, monkeypatch
) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    def fake_get_presigned_url(
        self, storage_key: str, expires_in: int | None = None
    ) -> str:
        raise AssertionError("Missing file lookup should not reach presigned URL generation")

    monkeypatch.setattr(FileService, "get_presigned_url", fake_get_presigned_url)

    response = await client.get(f"/api/v1/files/{uuid.uuid4()}/url", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "File not found."


async def test_get_file_url_uses_configured_short_ttl(
    client, mock_user, db, monkeypatch
) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    file_id = uuid.uuid4()
    record = UploadedFile(
        id=file_id,
        user_id=mock_user.id,
        original_filename="resume.txt",
        content_type="text/plain",
        size_bytes=128,
        storage_key=f"{mock_user.id}/{file_id}.txt",
        status=FileStatus.ready,
    )
    db.add(record)
    await db.flush()

    captured: dict[str, int | str] = {}

    def fake_get_presigned_url(
        self, storage_key: str, expires_in: int | None = None
    ) -> str:
        ttl = expires_in or file_service_module.settings.FILE_DOWNLOAD_URL_TTL_SECONDS
        captured["storage_key"] = storage_key
        captured["ttl"] = ttl
        return f"https://download.example.test/{file_id}.txt?ttl={ttl}"

    monkeypatch.setattr(FileService, "get_presigned_url", fake_get_presigned_url)

    response = await client.get(f"/api/v1/files/{file_id}/url", headers=headers)

    assert response.status_code == 200
    assert captured == {
        "storage_key": record.storage_key,
        "ttl": file_service_module.settings.FILE_DOWNLOAD_URL_TTL_SECONDS,
    }
    assert response.json()["url"].endswith(
        f"ttl={file_service_module.settings.FILE_DOWNLOAD_URL_TTL_SECONDS}"
    )
