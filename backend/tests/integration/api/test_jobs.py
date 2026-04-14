import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.models.job_description import JobDescription
from app.models.user import User


async def _login(client, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


async def test_create_job_persists_and_returns_normalized_fields(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    response = await client.post(
        "/api/v1/jobs",
        headers=headers,
        json={
            "title": "  Senior Backend Engineer  ",
            "company": "   ",
            "raw_text": "\n  Build APIs and improve reliability.  \n",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert uuid.UUID(payload["id"])
    assert payload["user_id"] == str(mock_user.id)
    assert payload["title"] == "Senior Backend Engineer"
    assert payload["company"] is None
    assert payload["raw_text"] == "Build APIs and improve reliability."
    assert payload["parsed_at"] is None

    result = await db.execute(
        select(JobDescription).where(JobDescription.id == uuid.UUID(payload["id"]))
    )
    job = result.scalar_one()
    assert job.user_id == mock_user.id
    assert job.title == "Senior Backend Engineer"
    assert job.company is None
    assert job.raw_text == "Build APIs and improve reliability."


async def test_job_create_list_and_detail_require_auth(client, mock_user, db) -> None:
    job = JobDescription(
        user_id=mock_user.id,
        title="Platform Engineer",
        company="CareerCore",
        raw_text="Own internal platform systems.",
    )
    db.add(job)
    await db.flush()

    create_response = await client.post(
        "/api/v1/jobs",
        json={"title": "Unauthorized", "company": "Nope", "raw_text": "Should fail"},
    )
    list_response = await client.get("/api/v1/jobs")
    detail_response = await client.get(f"/api/v1/jobs/{job.id}")

    assert create_response.status_code in (401, 403)
    assert list_response.status_code in (401, 403)
    assert detail_response.status_code in (401, 403)


async def test_job_list_and_detail_enforce_ownership(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    other_user = User(
        id=uuid.uuid4(),
        email="otheruser@careercore.test",
        password_hash=hash_password("Otherpassword123"),
        is_active=True,
    )
    db.add(other_user)
    await db.flush()

    my_job = JobDescription(
        user_id=mock_user.id,
        title="My Job",
        company="CareerCore",
        raw_text="My job description.",
    )
    other_job = JobDescription(
        user_id=other_user.id,
        title="Other Job",
        company="External Co",
        raw_text="Other user's job description.",
    )
    db.add_all([my_job, other_job])
    await db.flush()

    list_response = await client.get("/api/v1/jobs", headers=headers)
    assert list_response.status_code == 200
    jobs = list_response.json()
    assert [job["id"] for job in jobs] == [str(my_job.id)]

    own_detail_response = await client.get(f"/api/v1/jobs/{my_job.id}", headers=headers)
    assert own_detail_response.status_code == 200
    assert own_detail_response.json()["id"] == str(my_job.id)

    other_detail_response = await client.get(f"/api/v1/jobs/{other_job.id}", headers=headers)
    assert other_detail_response.status_code == 404
    assert other_detail_response.json()["detail"] == "Job not found."
