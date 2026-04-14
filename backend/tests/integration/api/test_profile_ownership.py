import uuid
from datetime import date

from app.core.security import hash_password
from app.models.certification import Certification
from app.models.profile import Profile
from app.models.project import Project
from app.models.skill import Skill
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


async def _make_other_user_with_profile(db) -> tuple[User, Profile]:
    other_user = User(
        id=uuid.uuid4(),
        email="other-owner@careercore.test",
        password_hash=hash_password("Otherpassword123"),
        is_active=True,
    )
    other_profile = Profile(
        id=uuid.uuid4(),
        user_id=other_user.id,
        display_name="Other User",
        completeness_pct=0.0,
    )
    db.add_all([other_user, other_profile])
    await db.flush()
    return other_user, other_profile


async def test_profile_get_and_patch_only_return_authenticated_users_profile(
    client, mock_user, mock_profile
) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    response = await client.get("/api/v1/profile", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(mock_profile.id)
    assert response.json()["user_id"] == str(mock_user.id)

    patch_response = await client.patch(
        "/api/v1/profile",
        headers=headers,
        json={
            "display_name": "Test User Updated",
            "current_title": "Senior Engineer",
        },
    )
    assert patch_response.status_code == 200
    payload = patch_response.json()
    assert payload["id"] == str(mock_profile.id)
    assert payload["user_id"] == str(mock_user.id)
    assert payload["display_name"] == "Test User Updated"
    assert payload["current_title"] == "Senior Engineer"


async def test_profile_subentity_list_endpoints_only_return_authenticated_users_data(
    client, mock_user, mock_profile, db
) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    _, other_profile = await _make_other_user_with_profile(db)

    owned_experience = WorkExperience(
        id=uuid.uuid4(),
        profile_id=mock_profile.id,
        employer="CareerCore",
        role_title="Backend Engineer",
        start_date=date(2024, 1, 1),
        is_current=False,
    )
    foreign_experience = WorkExperience(
        id=uuid.uuid4(),
        profile_id=other_profile.id,
        employer="Other Co",
        role_title="Engineer",
        start_date=date(2024, 1, 1),
        is_current=False,
    )
    owned_project = Project(
        id=uuid.uuid4(),
        profile_id=mock_profile.id,
        name="Owned Project",
    )
    foreign_project = Project(
        id=uuid.uuid4(),
        profile_id=other_profile.id,
        name="Foreign Project",
    )
    owned_skill = Skill(
        id=uuid.uuid4(),
        profile_id=mock_profile.id,
        name="Python",
    )
    foreign_skill = Skill(
        id=uuid.uuid4(),
        profile_id=other_profile.id,
        name="Go",
    )
    owned_cert = Certification(
        id=uuid.uuid4(),
        profile_id=mock_profile.id,
        name="AWS Certified Developer",
    )
    foreign_cert = Certification(
        id=uuid.uuid4(),
        profile_id=other_profile.id,
        name="CKA",
    )
    db.add_all(
        [
            owned_experience,
            foreign_experience,
            owned_project,
            foreign_project,
            owned_skill,
            foreign_skill,
            owned_cert,
            foreign_cert,
        ]
    )
    await db.flush()

    experiences = await client.get("/api/v1/profile/experience", headers=headers)
    projects = await client.get("/api/v1/profile/projects", headers=headers)
    skills = await client.get("/api/v1/profile/skills", headers=headers)
    certs = await client.get("/api/v1/profile/certifications", headers=headers)

    assert [item["id"] for item in experiences.json()] == [str(owned_experience.id)]
    assert [item["id"] for item in projects.json()] == [str(owned_project.id)]
    assert [item["id"] for item in skills.json()] == [str(owned_skill.id)]
    assert [item["id"] for item in certs.json()] == [str(owned_cert.id)]


async def test_profile_subentity_cross_user_updates_and_deletes_return_403(
    client, mock_user, db
) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    _, other_profile = await _make_other_user_with_profile(db)

    foreign_experience = WorkExperience(
        id=uuid.uuid4(),
        profile_id=other_profile.id,
        employer="Other Co",
        role_title="Engineer",
        start_date=date(2024, 1, 1),
        is_current=False,
    )
    foreign_project = Project(
        id=uuid.uuid4(),
        profile_id=other_profile.id,
        name="Foreign Project",
    )
    foreign_skill = Skill(
        id=uuid.uuid4(),
        profile_id=other_profile.id,
        name="Go",
    )
    foreign_cert = Certification(
        id=uuid.uuid4(),
        profile_id=other_profile.id,
        name="CKA",
    )
    db.add_all([foreign_experience, foreign_project, foreign_skill, foreign_cert])
    await db.flush()

    responses = [
        await client.patch(
            f"/api/v1/profile/experience/{foreign_experience.id}",
            headers=headers,
            json={"role_title": "Senior Engineer"},
        ),
        await client.delete(f"/api/v1/profile/experience/{foreign_experience.id}", headers=headers),
        await client.patch(
            f"/api/v1/profile/projects/{foreign_project.id}",
            headers=headers,
            json={"name": "Owned Now"},
        ),
        await client.delete(f"/api/v1/profile/projects/{foreign_project.id}", headers=headers),
        await client.patch(
            f"/api/v1/profile/skills/{foreign_skill.id}",
            headers=headers,
            json={"name": "Rust"},
        ),
        await client.delete(f"/api/v1/profile/skills/{foreign_skill.id}", headers=headers),
        await client.patch(
            f"/api/v1/profile/certifications/{foreign_cert.id}",
            headers=headers,
            json={"issuer": "CNCF"},
        ),
        await client.delete(
            f"/api/v1/profile/certifications/{foreign_cert.id}",
            headers=headers,
        ),
    ]

    assert all(response.status_code == 403 for response in responses)
    assert all(response.json()["detail"] == "Forbidden." for response in responses)


async def test_work_experience_rejects_cross_user_source_file_with_403(
    client, mock_user, mock_profile, db
) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    other_user, _ = await _make_other_user_with_profile(db)

    other_file = UploadedFile(
        id=uuid.uuid4(),
        user_id=other_user.id,
        original_filename="other.pdf",
        content_type="application/pdf",
        size_bytes=200,
        storage_key=f"{other_user.id}/other.pdf",
        status=FileStatus.ready,
    )
    owned_experience = WorkExperience(
        id=uuid.uuid4(),
        profile_id=mock_profile.id,
        employer="CareerCore",
        role_title="Engineer",
        start_date=date(2024, 1, 1),
        is_current=False,
    )
    db.add_all([other_file, owned_experience])
    await db.flush()

    create_response = await client.post(
        "/api/v1/profile/experience",
        headers=headers,
        json={
            "source_file_id": str(other_file.id),
            "employer": "CareerCore",
            "role_title": "Backend Engineer",
            "start_date": "2024-01-01",
        },
    )
    assert create_response.status_code == 403
    assert create_response.json()["detail"] == "Forbidden."

    update_response = await client.patch(
        f"/api/v1/profile/experience/{owned_experience.id}",
        headers=headers,
        json={"source_file_id": str(other_file.id)},
    )
    assert update_response.status_code == 403
    assert update_response.json()["detail"] == "Forbidden."
