import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.models.profile import Profile
from app.models.resume import Resume, ResumeBullet
from app.models.user import User


async def _login(client, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


async def _make_other_user_with_profile(db) -> tuple[User, Profile]:
    other_user = User(
        id=uuid.uuid4(),
        email="other-resume-owner@careercore.test",
        password_hash=hash_password("Otherpassword123"),
        is_active=True,
    )
    other_profile = Profile(
        id=uuid.uuid4(),
        user_id=other_user.id,
        display_name="Other User",
        completeness_pct=0.0,
    )
    db.add_all([other_user, other_profile])
    await db.flush()
    return other_user, other_profile


async def test_approve_bullet_returns_approved_bullet(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    resume = Resume(id=uuid.uuid4(), user_id=mock_user.id, job_id=None)
    bullet = ResumeBullet(
        id=uuid.uuid4(),
        resume_id=resume.id,
        text="Generated bullet",
        is_ai_generated=True,
        is_approved=False,
        confidence=0.88,
    )
    db.add_all([resume, bullet])
    await db.flush()

    response = await client.patch(
        f"/api/v1/resumes/{resume.id}/bullets/{bullet.id}/approve",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(bullet.id)
    assert payload["resume_id"] == str(resume.id)
    assert payload["is_approved"] is True
    assert payload["is_ai_generated"] is True

    refreshed = await db.get(ResumeBullet, bullet.id)
    assert refreshed is not None
    assert refreshed.is_approved is True


async def test_approve_bullet_returns_404_for_other_users_bullet(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    other_user, _ = await _make_other_user_with_profile(db)
    other_resume = Resume(id=uuid.uuid4(), user_id=other_user.id, job_id=None)
    other_bullet = ResumeBullet(
        id=uuid.uuid4(),
        resume_id=other_resume.id,
        text="Other user's bullet",
        is_ai_generated=True,
        is_approved=False,
        confidence=0.5,
    )
    db.add_all([other_resume, other_bullet])
    await db.flush()

    response = await client.patch(
        f"/api/v1/resumes/{other_resume.id}/bullets/{other_bullet.id}/approve",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Bullet not found."


async def test_reject_bullet_returns_204_and_deletes_bullet(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    resume = Resume(id=uuid.uuid4(), user_id=mock_user.id, job_id=None)
    bullet = ResumeBullet(
        id=uuid.uuid4(),
        resume_id=resume.id,
        text="Generated bullet",
        is_ai_generated=True,
        is_approved=False,
        confidence=0.71,
    )
    db.add_all([resume, bullet])
    await db.flush()

    response = await client.delete(
        f"/api/v1/resumes/{resume.id}/bullets/{bullet.id}",
        headers=headers,
    )

    assert response.status_code == 204
    assert response.content == b""

    deleted = await db.get(ResumeBullet, bullet.id)
    assert deleted is None


async def test_reject_bullet_returns_404_for_other_users_bullet(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")
    other_user, _ = await _make_other_user_with_profile(db)
    other_resume = Resume(id=uuid.uuid4(), user_id=other_user.id, job_id=None)
    other_bullet = ResumeBullet(
        id=uuid.uuid4(),
        resume_id=other_resume.id,
        text="Other user's bullet",
        is_ai_generated=True,
        is_approved=False,
        confidence=0.42,
    )
    db.add_all([other_resume, other_bullet])
    await db.flush()

    response = await client.delete(
        f"/api/v1/resumes/{other_resume.id}/bullets/{other_bullet.id}",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Bullet not found."

    still_present = await db.execute(
        select(ResumeBullet).where(ResumeBullet.id == other_bullet.id)
    )
    assert still_present.scalar_one_or_none() is not None
