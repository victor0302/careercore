import uuid
from datetime import datetime

from app.core.security import hash_password
from app.models.resume import Resume, ResumeBullet
from app.models.user import User


async def _login(client, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_snapshot_version_returns_201_with_created_at(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    resume = Resume(user_id=mock_user.id, job_id=None)
    db.add(resume)
    await db.flush()

    db.add(
        ResumeBullet(
            resume_id=resume.id,
            text="Led API redesign with measurable reliability gains.",
            is_ai_generated=True,
            is_approved=True,
            confidence=0.92,
        )
    )
    await db.flush()

    response = await client.post(
        f"/api/v1/resumes/{resume.id}/versions",
        headers=headers,
        json={"fit_score": 88.0},
    )

    assert response.status_code == 201
    payload = response.json()
    assert uuid.UUID(payload["id"])
    assert payload["resume_id"] == str(resume.id)
    assert payload["fit_score_at_gen"] == 88.0
    assert datetime.fromisoformat(payload["created_at"].replace("Z", "+00:00"))


async def test_snapshot_version_returns_422_when_no_approved_bullets(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    resume = Resume(user_id=mock_user.id, job_id=None)
    db.add(resume)
    await db.flush()

    db.add(
        ResumeBullet(
            resume_id=resume.id,
            text="Still draft.",
            is_ai_generated=True,
            is_approved=False,
            confidence=0.48,
        )
    )
    await db.flush()

    response = await client.post(
        f"/api/v1/resumes/{resume.id}/versions",
        headers=headers,
        json={"fit_score": 40.0},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "No approved bullets to snapshot."


async def test_snapshot_version_returns_404_for_other_users_resume(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    other_user = User(
        id=uuid.uuid4(),
        email="resume-owner@careercore.test",
        password_hash=hash_password("Otherpassword123"),
        is_active=True,
    )
    db.add(other_user)
    await db.flush()

    other_resume = Resume(user_id=other_user.id, job_id=None)
    db.add(other_resume)
    await db.flush()

    db.add(
        ResumeBullet(
            resume_id=other_resume.id,
            text="Private approved bullet.",
            is_ai_generated=False,
            is_approved=True,
            confidence=None,
        )
    )
    await db.flush()

    response = await client.post(
        f"/api/v1/resumes/{other_resume.id}/versions",
        headers=headers,
        json={"fit_score": 91.0},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Resume not found."
