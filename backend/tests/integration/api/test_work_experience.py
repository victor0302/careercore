import uuid
from datetime import date

from app.core.security import hash_password
from app.models.profile import Profile
from app.models.uploaded_file import FileStatus, UploadedFile
from app.models.user import User
from app.models.work_experience import WorkExperience


async def _login(client, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


async def test_work_experience_crud_round_trip_includes_source_file_id(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    profile = Profile(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        completeness_pct=0.0,
    )
    source_file = UploadedFile(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        original_filename="resume.pdf",
        content_type="application/pdf",
        size_bytes=100,
        storage_key=f"{mock_user.id}/resume.pdf",
        status=FileStatus.ready,
    )
    db.add_all([profile, source_file])
    await db.flush()

    create_response = await client.post(
        "/api/v1/profile/experience",
        headers=headers,
        json={
            "source_file_id": str(source_file.id),
            "employer": "CareerCore",
            "role_title": "Backend Engineer",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "is_current": False,
            "description_raw": "Built APIs.",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    experience_id = created["id"]
    assert created["source_file_id"] == str(source_file.id)

    list_response = await client.get("/api/v1/profile/experience", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == experience_id

    update_response = await client.patch(
        f"/api/v1/profile/experience/{experience_id}",
        headers=headers,
        json={"source_file_id": None, "end_date": None, "description_raw": None},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["source_file_id"] is None
    assert updated["end_date"] is None
    assert updated["description_raw"] is None

    delete_response = await client.delete(
        f"/api/v1/profile/experience/{experience_id}",
        headers=headers,
    )
    assert delete_response.status_code == 204

    final_list_response = await client.get("/api/v1/profile/experience", headers=headers)
    assert final_list_response.status_code == 200
    assert final_list_response.json() == []


async def test_work_experience_rejects_other_users_source_file(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    profile = Profile(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        completeness_pct=0.0,
    )
    other_user = User(
        id=uuid.uuid4(),
        email="other-file-owner@careercore.test",
        password_hash=hash_password("Otherpassword123"),
        is_active=True,
    )
    other_file = UploadedFile(
        id=uuid.uuid4(),
        user_id=other_user.id,
        original_filename="other.pdf",
        content_type="application/pdf",
        size_bytes=200,
        storage_key=f"{other_user.id}/other.pdf",
        status=FileStatus.ready,
    )
    db.add_all([profile, other_user, other_file])
    await db.flush()

    create_response = await client.post(
        "/api/v1/profile/experience",
        headers=headers,
        json={
            "source_file_id": str(other_file.id),
            "employer": "CareerCore",
            "role_title": "Backend Engineer",
            "start_date": str(date(2024, 1, 1)),
        },
    )
    assert create_response.status_code == 403
    assert create_response.json()["detail"] == "Forbidden."

    experience = WorkExperience(
        id=uuid.uuid4(),
        profile_id=profile.id,
        employer="CareerCore",
        role_title="Engineer",
        start_date=date(2024, 1, 1),
        is_current=False,
    )
    db.add(experience)
    await db.flush()

    update_response = await client.patch(
        f"/api/v1/profile/experience/{experience.id}",
        headers=headers,
        json={"source_file_id": str(other_file.id)},
    )
    assert update_response.status_code == 403
    assert update_response.json()["detail"] == "Forbidden."
