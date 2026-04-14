from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.security import ALGORITHM, settings


async def test_protected_route_without_token_returns_401(client) -> None:
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"
    assert response.headers["www-authenticate"] == "Bearer"


async def test_protected_route_with_expired_token_returns_401(client, mock_user) -> None:
    expired_token = jwt.encode(
        {
            "sub": str(mock_user.id),
            "iat": datetime.now(tz=timezone.utc) - timedelta(minutes=10),
            "exp": datetime.now(tz=timezone.utc) - timedelta(minutes=5),
            "type": "access",
        },
        settings.JWT_SECRET_KEY,
        algorithm=ALGORITHM,
    )

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"
    assert response.headers["www-authenticate"] == "Bearer"


async def test_health_route_is_public(client) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code in (200, 503)
