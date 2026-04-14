async def _login(client, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def _assert_validation_error(response, expected_status: int = 422) -> None:
    assert response.status_code == expected_status
    payload = response.json()
    assert isinstance(payload.get("detail"), list)
    assert payload["detail"]


async def test_auth_register_validation_errors_return_422(client) -> None:
    missing_email = await client.post(
        "/api/v1/auth/register",
        json={"password": "Password123"},
    )
    invalid_email = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "Password123"},
    )
    short_password = await client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": "Short1"},
    )

    _assert_validation_error(missing_email)
    _assert_validation_error(invalid_email)
    _assert_validation_error(short_password)


async def test_auth_login_validation_errors_return_422(client) -> None:
    missing_password = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com"},
    )
    empty_body = await client.post("/api/v1/auth/login", json={})

    _assert_validation_error(missing_password)
    _assert_validation_error(empty_body)


async def test_jobs_create_validation_errors_return_422(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    missing_title = await client.post(
        "/api/v1/jobs",
        headers=headers,
        json={"raw_text": "Build reliable APIs."},
    )
    missing_description = await client.post(
        "/api/v1/jobs",
        headers=headers,
        json={"title": "Backend Engineer"},
    )
    title_too_long = await client.post(
        "/api/v1/jobs",
        headers=headers,
        json={"title": "x" * 256, "raw_text": "Build reliable APIs."},
    )

    _assert_validation_error(missing_title)
    _assert_validation_error(missing_description)
    _assert_validation_error(title_too_long)


async def test_work_experience_validation_errors_return_422(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    missing_employer = await client.post(
        "/api/v1/profile/experience",
        headers=headers,
        json={"role_title": "Engineer", "start_date": "2024-01-01"},
    )
    missing_role_title = await client.post(
        "/api/v1/profile/experience",
        headers=headers,
        json={"employer": "CareerCore", "start_date": "2024-01-01"},
    )
    bad_start_date = await client.post(
        "/api/v1/profile/experience",
        headers=headers,
        json={
            "employer": "CareerCore",
            "role_title": "Engineer",
            "start_date": "not-a-date",
        },
    )

    _assert_validation_error(missing_employer)
    _assert_validation_error(missing_role_title)
    _assert_validation_error(bad_start_date)


async def test_projects_validation_errors_return_422(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    missing_name = await client.post(
        "/api/v1/profile/projects",
        headers=headers,
        json={"description_raw": "Built something useful."},
    )

    _assert_validation_error(missing_name)


async def test_skills_validation_errors_return_422(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    missing_name = await client.post(
        "/api/v1/profile/skills",
        headers=headers,
        json={"category": "Programming"},
    )

    _assert_validation_error(missing_name)


async def test_certifications_validation_errors_return_422(client, mock_user) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    missing_name = await client.post(
        "/api/v1/profile/certifications",
        headers=headers,
        json={"issuer": "AWS"},
    )

    _assert_validation_error(missing_name)
