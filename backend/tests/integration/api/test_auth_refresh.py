async def test_refresh_rotates_cookie_and_returns_new_access_token(client, mock_user) -> None:
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": mock_user.email, "password": "testpassword123"},
    )
    assert login_response.status_code == 200
    old_cookie = login_response.cookies.get("refresh_token")
    assert old_cookie is not None

    refresh_response = await client.post("/api/v1/auth/refresh", json={})

    assert refresh_response.status_code == 200
    payload = refresh_response.json()
    assert set(payload) == {"access_token", "token_type"}
    assert payload["token_type"] == "bearer"
    assert "refresh_token=" in refresh_response.headers["set-cookie"]
    assert refresh_response.cookies.get("refresh_token") != old_cookie


async def test_refresh_rejects_replayed_token(client, mock_user) -> None:
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": mock_user.email, "password": "testpassword123"},
    )
    old_cookie = login_response.cookies.get("refresh_token")
    assert old_cookie is not None

    first_refresh = await client.post("/api/v1/auth/refresh", json={})
    assert first_refresh.status_code == 200

    replay_response = await client.post(
        "/api/v1/auth/refresh",
        json={},
        cookies={"refresh_token": old_cookie},
    )
    assert replay_response.status_code == 401
    assert replay_response.json()["detail"] == "Invalid or expired refresh token."
