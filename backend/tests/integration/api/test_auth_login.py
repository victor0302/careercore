from sqlalchemy import select

from app.models.audit_log import AuditLog


async def test_login_returns_access_token_and_sets_refresh_cookie(client, mock_user, db) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": mock_user.email, "password": "testpassword123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"access_token", "token_type"}
    assert payload["token_type"] == "bearer"
    assert "refresh_token=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]

    result = await db.execute(select(AuditLog).where(AuditLog.action == "user.login"))
    logs = list(result.scalars())
    assert len(logs) == 1
    assert logs[0].user_id == mock_user.id


async def test_login_wrong_password_returns_same_401_and_logs_failure(
    client, mock_user, db
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": mock_user.email, "password": "wrongpassword123"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."

    result = await db.execute(select(AuditLog).where(AuditLog.action == "user.login.failed"))
    logs = list(result.scalars())
    assert len(logs) == 1


async def test_login_wrong_email_returns_same_401_and_logs_failure(client, db) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "missing@careercore.test", "password": "wrongpassword123"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."

    result = await db.execute(select(AuditLog).where(AuditLog.action == "user.login.failed"))
    logs = list(result.scalars())
    assert len(logs) == 1
