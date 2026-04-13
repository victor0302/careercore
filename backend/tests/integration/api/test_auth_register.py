from sqlalchemy import select

from app.models.profile import Profile
from app.models.user import User


async def test_register_creates_user_and_profile(client, db) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "newuser@careercore.test", "password": "StrongPass123"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert set(payload) == {"id", "email"}
    assert payload["email"] == "newuser@careercore.test"

    user_result = await db.execute(select(User).where(User.email == "newuser@careercore.test"))
    user = user_result.scalar_one()
    assert user.password_hash != "StrongPass123"
    assert user.password_hash

    profile_result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    profile = profile_result.scalar_one()
    assert profile.user_id == user.id
    assert profile.completeness_pct == 0.0


async def test_register_rejects_duplicate_email(client) -> None:
    payload = {"email": "dupe@careercore.test", "password": "StrongPass123"}

    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409
    assert second.json()["detail"] == "A user with this email already exists."


async def test_register_rejects_weak_password(client) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "weak@careercore.test", "password": "alllowercase"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any("uppercase letter" in err["msg"] for err in detail)
