import uuid
from datetime import datetime, timedelta, timezone

from app.core.security import hash_password
from app.models.job_description import JobDescription
from app.models.resume import Resume, ResumeVersion
from app.models.user import User


async def _login(client, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_list_resume_versions_returns_only_authenticated_users_versions(
    client, mock_user, db
) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    own_job = JobDescription(
        user_id=mock_user.id,
        title="Backend Engineer",
        company="CareerCore",
        raw_text="Build APIs.",
    )
    own_resume = Resume(user_id=mock_user.id, job=own_job)
    db.add_all([own_job, own_resume])
    await db.flush()

    own_version = ResumeVersion(
        resume_id=own_resume.id,
        fit_score_at_gen=88.0,
        created_at=datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
    )

    other_user = User(
        id=uuid.uuid4(),
        email="other-versions@careercore.test",
        password_hash=hash_password("Otherpassword123"),
        is_active=True,
    )
    other_job = JobDescription(
        user_id=other_user.id,
        title="Staff Engineer",
        company="External Co",
        raw_text="Lead platform work.",
    )
    other_resume = Resume(user_id=other_user.id, job=other_job)
    other_version = ResumeVersion(
        resume_id=other_resume.id,
        fit_score_at_gen=94.0,
        created_at=datetime(2026, 4, 15, 13, 0, tzinfo=timezone.utc),
    )
    db.add_all([own_version, other_user, other_job, other_resume, other_version])
    await db.flush()

    response = await client.get("/api/v1/resumes/versions", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == str(own_version.id)
    assert payload[0]["resume_id"] == str(own_resume.id)
    assert payload[0]["fit_score_at_gen"] == 88.0
    assert payload[0]["job_title"] == "Backend Engineer"
    assert payload[0]["job_company"] == "CareerCore"
    assert payload[0]["created_at"] == "2026-04-15T12:00:00Z"


async def test_list_resume_versions_paginates_results(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    resume = Resume(user_id=mock_user.id, job_id=None)
    db.add(resume)
    await db.flush()

    base_time = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    versions = [
        ResumeVersion(
            resume_id=resume.id,
            fit_score_at_gen=60.0 + index,
            created_at=base_time + timedelta(minutes=index),
        )
        for index in range(3)
    ]
    db.add_all(versions)
    await db.flush()

    response = await client.get("/api/v1/resumes/versions?skip=1&limit=1", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == str(versions[1].id)
    assert payload[0]["fit_score_at_gen"] == 61.0
    assert payload[0]["job_title"] is None
    assert payload[0]["job_company"] is None
    assert payload[0]["created_at"] == "2026-04-15T10:01:00Z"


async def test_list_resume_versions_returns_empty_list_for_user_without_versions(
    client, mock_user
) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    response = await client.get("/api/v1/resumes/versions", headers=headers)

    assert response.status_code == 200
    assert response.json() == []
