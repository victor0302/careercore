async def test_me_returns_current_user(client, mock_user) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": mock_user.email, "password": "testpassword123"},
    )
    assert login.status_code == 200
    access_token = login.json()["access_token"]

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(mock_user.id)
    assert payload["email"] == mock_user.email


async def test_me_requires_auth(client) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 403
