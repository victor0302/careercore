"""Integration tests for Certification CRUD endpoints."""

import uuid

from app.core.security import hash_password
from app.models.certification import Certification
from app.models.profile import Profile
from app.models.user import User


async def _login(client, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_certification_crud_round_trip(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    # Create with date fields
    create_response = await client.post(
        "/api/v1/profile/certifications",
        headers=headers,
        json={
            "name": "AWS Solutions Architect",
            "issuer": "Amazon Web Services",
            "issued_date": "2023-06-15",
            "expiry_date": "2026-06-15",
            "credential_id": "AWS-SAA-12345",
            "credential_url": "https://aws.amazon.com/verify/12345",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    cert_id = created["id"]
    assert created["name"] == "AWS Solutions Architect"
    assert created["issuer"] == "Amazon Web Services"
    # ISO date strings round-trip correctly
    assert created["issued_date"] == "2023-06-15"
    assert created["expiry_date"] == "2026-06-15"
    assert created["credential_id"] == "AWS-SAA-12345"

    # List
    list_response = await client.get("/api/v1/profile/certifications", headers=headers)
    assert list_response.status_code == 200
    ids = [c["id"] for c in list_response.json()]
    assert cert_id in ids

    # Update
    update_response = await client.patch(
        f"/api/v1/profile/certifications/{cert_id}",
        headers=headers,
        json={"issuer": "AWS (Updated)", "expiry_date": "2027-06-15"},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["issuer"] == "AWS (Updated)"
    assert updated["expiry_date"] == "2027-06-15"

    # Delete
    delete_response = await client.delete(
        f"/api/v1/profile/certifications/{cert_id}",
        headers=headers,
    )
    assert delete_response.status_code == 204

    # Gone after delete
    final_list = await client.get("/api/v1/profile/certifications", headers=headers)
    assert all(c["id"] != cert_id for c in final_list.json())


async def test_certification_date_fields_are_optional(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    response = await client.post(
        "/api/v1/profile/certifications",
        headers=headers,
        json={"name": "Internal Training"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["issued_date"] is None
    assert body["expiry_date"] is None


async def test_certification_list_returns_empty_for_new_user(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    response = await client.get("/api/v1/profile/certifications", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_certification_create_requires_name(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    response = await client.post(
        "/api/v1/profile/certifications",
        headers=headers,
        json={"issuer": "Missing name field."},
    )
    assert response.status_code == 422


async def test_certification_update_404_for_unknown_id(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    response = await client.patch(
        f"/api/v1/profile/certifications/{uuid.uuid4()}",
        headers=headers,
        json={"name": "Ghost"},
    )
    assert response.status_code == 404


async def test_certification_ownership_rejection(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    other_user = User(
        id=uuid.uuid4(),
        email="other-cert@careercore.test",
        password_hash=hash_password("Otherpassword123"),
        is_active=True,
    )
    other_profile = Profile(id=uuid.uuid4(), user_id=other_user.id, completeness_pct=0.0)
    other_cert = Certification(
        id=uuid.uuid4(),
        profile_id=other_profile.id,
        name="Other's certification",
    )
    db.add_all([other_user, other_profile, other_cert])
    await db.flush()

    patch_response = await client.patch(
        f"/api/v1/profile/certifications/{other_cert.id}",
        headers=headers,
        json={"name": "Hijacked"},
    )
    assert patch_response.status_code == 403
    assert patch_response.json()["detail"] == "Forbidden."

    delete_response = await client.delete(
        f"/api/v1/profile/certifications/{other_cert.id}",
        headers=headers,
    )
    assert delete_response.status_code == 403
    assert delete_response.json()["detail"] == "Forbidden."
