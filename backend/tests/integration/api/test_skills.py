"""Integration tests for Skill CRUD endpoints."""

import uuid

from app.core.security import hash_password
from app.models.profile import Profile
from app.models.skill import Skill
from app.models.user import User


async def _login(client, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_skill_crud_round_trip(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    # Create
    create_response = await client.post(
        "/api/v1/profile/skills",
        headers=headers,
        json={
            "name": "Python",
            "category": "Programming",
            "proficiency_level": "expert",
            "years_of_experience": 5.0,
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    skill_id = created["id"]
    assert created["name"] == "Python"
    assert created["category"] == "Programming"
    assert created["proficiency_level"] == "expert"
    assert created["years_of_experience"] == 5.0

    # List
    list_response = await client.get("/api/v1/profile/skills", headers=headers)
    assert list_response.status_code == 200
    ids = [s["id"] for s in list_response.json()]
    assert skill_id in ids

    # Update
    update_response = await client.patch(
        f"/api/v1/profile/skills/{skill_id}",
        headers=headers,
        json={"proficiency_level": "intermediate", "years_of_experience": 3.0},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["proficiency_level"] == "intermediate"
    assert updated["years_of_experience"] == 3.0

    # Delete
    delete_response = await client.delete(
        f"/api/v1/profile/skills/{skill_id}",
        headers=headers,
    )
    assert delete_response.status_code == 204

    # Gone after delete
    final_list = await client.get("/api/v1/profile/skills", headers=headers)
    assert all(s["id"] != skill_id for s in final_list.json())


async def test_skill_list_returns_empty_for_new_user(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    response = await client.get("/api/v1/profile/skills", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_skill_create_requires_name(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    response = await client.post(
        "/api/v1/profile/skills",
        headers=headers,
        json={"category": "Missing name field."},
    )
    assert response.status_code == 422


async def test_skill_update_404_for_unknown_id(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    response = await client.patch(
        f"/api/v1/profile/skills/{uuid.uuid4()}",
        headers=headers,
        json={"name": "Ghost"},
    )
    assert response.status_code == 404


async def test_skill_ownership_rejection(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    other_user = User(
        id=uuid.uuid4(),
        email="other-skill@careercore.test",
        password_hash=hash_password("Otherpassword123"),
        is_active=True,
    )
    other_profile = Profile(id=uuid.uuid4(), user_id=other_user.id, completeness_pct=0.0)
    other_skill = Skill(
        id=uuid.uuid4(),
        profile_id=other_profile.id,
        name="Other's skill",
    )
    db.add_all([other_user, other_profile, other_skill])
    await db.flush()

    patch_response = await client.patch(
        f"/api/v1/profile/skills/{other_skill.id}",
        headers=headers,
        json={"name": "Hijacked"},
    )
    assert patch_response.status_code == 403
    assert patch_response.json()["detail"] == "Forbidden."

    delete_response = await client.delete(
        f"/api/v1/profile/skills/{other_skill.id}",
        headers=headers,
    )
    assert delete_response.status_code == 403
    assert delete_response.json()["detail"] == "Forbidden."
