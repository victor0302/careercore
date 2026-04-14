from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.refresh_token import RefreshToken


async def test_logout_returns_204_and_clears_cookie(client, mock_user) -> None:
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": mock_user.email, "password": "testpassword123"},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 204
    # The Set-Cookie header should clear the refresh_token cookie
    set_cookie = response.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    assert 'Max-Age=0' in set_cookie or 'expires=' in set_cookie.lower()


async def test_logout_invalidates_refresh_token(client, mock_user, db) -> None:
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": mock_user.email, "password": "testpassword123"},
    )
    access_token = login_response.json()["access_token"]
    refresh_cookie = login_response.cookies.get("refresh_token")
    assert refresh_cookie is not None

    logout_response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_response.status_code == 204

    # The stored token must now be marked as used
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.user_id == mock_user.id)
    )
    tokens = list(result.scalars())
    assert all(t.used_at is not None for t in tokens)

    # Attempting to refresh with the old cookie must fail
    replay_response = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": refresh_cookie},
    )
    assert replay_response.status_code == 401


async def test_logout_writes_audit_log(client, mock_user, db) -> None:
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": mock_user.email, "password": "testpassword123"},
    )
    access_token = login_response.json()["access_token"]

    await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "user.logout")
    )
    logs = list(result.scalars())
    assert len(logs) == 1
    assert logs[0].user_id == mock_user.id


async def test_logout_without_token_returns_401(client) -> None:
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"
