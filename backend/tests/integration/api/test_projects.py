"""Integration tests for Project CRUD endpoints."""

import uuid

from app.core.security import hash_password
from app.models.profile import Profile
from app.models.project import Project
from app.models.user import User


async def _login(client, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_project_crud_round_trip(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    # Create
    create_response = await client.post(
        "/api/v1/profile/projects",
        headers=headers,
        json={"name": "CareerCore", "description_raw": "A job-fit platform.", "url": "https://example.com"},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    project_id = created["id"]
    assert created["name"] == "CareerCore"
    assert created["description_raw"] == "A job-fit platform."
    assert created["url"] == "https://example.com"

    # List
    list_response = await client.get("/api/v1/profile/projects", headers=headers)
    assert list_response.status_code == 200
    ids = [p["id"] for p in list_response.json()]
    assert project_id in ids

    # Update
    update_response = await client.patch(
        f"/api/v1/profile/projects/{project_id}",
        headers=headers,
        json={"description_raw": "Updated description."},
    )
    assert update_response.status_code == 200
    assert update_response.json()["description_raw"] == "Updated description."

    # Delete
    delete_response = await client.delete(
        f"/api/v1/profile/projects/{project_id}",
        headers=headers,
    )
    assert delete_response.status_code == 204

    # Gone after delete
    final_list = await client.get("/api/v1/profile/projects", headers=headers)
    assert all(p["id"] != project_id for p in final_list.json())


async def test_project_list_returns_empty_for_new_user(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    response = await client.get("/api/v1/profile/projects", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_project_create_requires_name(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    response = await client.post(
        "/api/v1/profile/projects",
        headers=headers,
        json={"description_raw": "Missing name field."},
    )
    assert response.status_code == 422


async def test_project_update_404_for_unknown_id(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    response = await client.patch(
        f"/api/v1/profile/projects/{uuid.uuid4()}",
        headers=headers,
        json={"name": "Ghost"},
    )
    assert response.status_code == 404


async def test_project_ownership_rejection(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    other_user = User(
        id=uuid.uuid4(),
        email="other-proj@careercore.test",
        password_hash=hash_password("Otherpassword123"),
        is_active=True,
    )
    other_profile = Profile(id=uuid.uuid4(), user_id=other_user.id, completeness_pct=0.0)
    other_project = Project(
        id=uuid.uuid4(),
        profile_id=other_profile.id,
        name="Other's project",
    )
    db.add_all([other_user, other_profile, other_project])
    await db.flush()

    patch_response = await client.patch(
        f"/api/v1/profile/projects/{other_project.id}",
        headers=headers,
        json={"name": "Hijacked"},
    )
    assert patch_response.status_code == 403
    assert patch_response.json()["detail"] == "Forbidden."

    delete_response = await client.delete(
        f"/api/v1/profile/projects/{other_project.id}",
        headers=headers,
    )
    assert delete_response.status_code == 403
    assert delete_response.json()["detail"] == "Forbidden."
