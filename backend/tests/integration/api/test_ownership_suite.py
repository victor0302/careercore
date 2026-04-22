"""Cross-user ownership enforcement integration suite.

Proves that user B cannot read or mutate any Phase 1 resource owned by user A.
Two real users are created per test using the shared ``db`` and ``client``
fixtures from conftest.py. Every cross-user attempt must return 403 or 404.

Existing coverage NOT duplicated here:
  - Profile GET/PATCH: test_profile_ownership.py
  - Resume create with cross-user job_id: test_resume_job_ownership.py
  - Job list/detail ownership check: test_jobs.py
"""

import uuid
from datetime import date

from app.core.security import hash_password
from app.models.certification import Certification
from app.models.job_description import JobDescription
from app.models.profile import Profile
from app.models.project import Project
from app.models.resume import Resume, ResumeBullet, ResumeVersion
from app.models.skill import Skill
from app.models.uploaded_file import FileStatus, UploadedFile
from app.models.user import User
from app.models.work_experience import WorkExperience
from app.services.file_service import FileService

_PASSWORD = "Ownertest1!"


async def _login(client, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _make_user(db, email: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(_PASSWORD),
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_profile(db, user_id: uuid.UUID) -> Profile:
    profile = Profile(
        id=uuid.uuid4(),
        user_id=user_id,
        completeness_pct=0.0,
    )
    db.add(profile)
    await db.flush()
    return profile


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


async def test_file_url_cross_user_returns_404(client, db, monkeypatch) -> None:
    user_a = await _make_user(db, "a-file@ownership.test")
    user_b = await _make_user(db, "b-file@ownership.test")

    file_id = uuid.uuid4()
    db.add(
        UploadedFile(
            id=file_id,
            user_id=user_a.id,
            original_filename="resume.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            storage_key=f"{user_a.id}/{file_id}.pdf",
            status=FileStatus.ready,
        )
    )
    await db.flush()

    def _deny_presigned(self, storage_key: str, expires_in: int | None = None) -> str:
        raise AssertionError("get_presigned_url must not be called for cross-user access")

    monkeypatch.setattr(FileService, "get_presigned_url", _deny_presigned)

    headers_b = await _login(client, user_b.email, _PASSWORD)
    response = await client.get(f"/api/v1/files/{file_id}/url", headers=headers_b)

    assert response.status_code == 404
    assert response.json()["detail"] == "File not found."


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


async def test_job_parse_cross_user_returns_404(client, db) -> None:
    user_a = await _make_user(db, "a-job@ownership.test")
    user_b = await _make_user(db, "b-job@ownership.test")

    job = JobDescription(
        user_id=user_a.id,
        title="Backend Engineer",
        company="CareerCore",
        raw_text="Build reliable backend systems.",
    )
    db.add(job)
    await db.flush()

    headers_b = await _login(client, user_b.email, _PASSWORD)
    response = await client.post(f"/api/v1/jobs/{job.id}/parse", headers=headers_b)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Work experience
# ---------------------------------------------------------------------------


async def test_work_experience_list_is_empty_for_cross_user(client, db) -> None:
    user_a = await _make_user(db, "a-exp-list@ownership.test")
    user_b = await _make_user(db, "b-exp-list@ownership.test")
    profile_a = await _make_profile(db, user_a.id)

    db.add(
        WorkExperience(
            id=uuid.uuid4(),
            profile_id=profile_a.id,
            employer="CareerCore",
            role_title="Engineer",
            start_date=date(2024, 1, 1),
            is_current=False,
        )
    )
    await db.flush()

    headers_b = await _login(client, user_b.email, _PASSWORD)
    response = await client.get("/api/v1/profile/experience", headers=headers_b)

    assert response.status_code == 200
    assert response.json() == []


async def test_work_experience_patch_and_delete_cross_user_return_403(client, db) -> None:
    user_a = await _make_user(db, "a-exp-mut@ownership.test")
    user_b = await _make_user(db, "b-exp-mut@ownership.test")
    profile_a = await _make_profile(db, user_a.id)

    exp = WorkExperience(
        id=uuid.uuid4(),
        profile_id=profile_a.id,
        employer="CareerCore",
        role_title="Engineer",
        start_date=date(2024, 1, 1),
        is_current=False,
    )
    db.add(exp)
    await db.flush()

    headers_b = await _login(client, user_b.email, _PASSWORD)

    patch_resp = await client.patch(
        f"/api/v1/profile/experience/{exp.id}",
        headers=headers_b,
        json={"role_title": "Intruder"},
    )
    delete_resp = await client.delete(
        f"/api/v1/profile/experience/{exp.id}",
        headers=headers_b,
    )

    assert patch_resp.status_code == 403
    assert patch_resp.json()["detail"] == "Forbidden."
    assert delete_resp.status_code == 403
    assert delete_resp.json()["detail"] == "Forbidden."


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


async def test_skills_list_is_empty_for_cross_user(client, db) -> None:
    user_a = await _make_user(db, "a-skill-list@ownership.test")
    user_b = await _make_user(db, "b-skill-list@ownership.test")
    profile_a = await _make_profile(db, user_a.id)

    db.add(Skill(id=uuid.uuid4(), profile_id=profile_a.id, name="Python"))
    await db.flush()

    headers_b = await _login(client, user_b.email, _PASSWORD)
    response = await client.get("/api/v1/profile/skills", headers=headers_b)

    assert response.status_code == 200
    assert response.json() == []


async def test_skills_patch_and_delete_cross_user_return_403(client, db) -> None:
    user_a = await _make_user(db, "a-skill-mut@ownership.test")
    user_b = await _make_user(db, "b-skill-mut@ownership.test")
    profile_a = await _make_profile(db, user_a.id)

    skill = Skill(id=uuid.uuid4(), profile_id=profile_a.id, name="Python")
    db.add(skill)
    await db.flush()

    headers_b = await _login(client, user_b.email, _PASSWORD)

    patch_resp = await client.patch(
        f"/api/v1/profile/skills/{skill.id}",
        headers=headers_b,
        json={"name": "Intruder"},
    )
    delete_resp = await client.delete(
        f"/api/v1/profile/skills/{skill.id}",
        headers=headers_b,
    )

    assert patch_resp.status_code == 403
    assert patch_resp.json()["detail"] == "Forbidden."
    assert delete_resp.status_code == 403
    assert delete_resp.json()["detail"] == "Forbidden."


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


async def test_projects_list_is_empty_for_cross_user(client, db) -> None:
    user_a = await _make_user(db, "a-proj-list@ownership.test")
    user_b = await _make_user(db, "b-proj-list@ownership.test")
    profile_a = await _make_profile(db, user_a.id)

    db.add(Project(id=uuid.uuid4(), profile_id=profile_a.id, name="CareerCore"))
    await db.flush()

    headers_b = await _login(client, user_b.email, _PASSWORD)
    response = await client.get("/api/v1/profile/projects", headers=headers_b)

    assert response.status_code == 200
    assert response.json() == []


async def test_projects_patch_and_delete_cross_user_return_403(client, db) -> None:
    user_a = await _make_user(db, "a-proj-mut@ownership.test")
    user_b = await _make_user(db, "b-proj-mut@ownership.test")
    profile_a = await _make_profile(db, user_a.id)

    project = Project(id=uuid.uuid4(), profile_id=profile_a.id, name="CareerCore")
    db.add(project)
    await db.flush()

    headers_b = await _login(client, user_b.email, _PASSWORD)

    patch_resp = await client.patch(
        f"/api/v1/profile/projects/{project.id}",
        headers=headers_b,
        json={"name": "Intruder"},
    )
    delete_resp = await client.delete(
        f"/api/v1/profile/projects/{project.id}",
        headers=headers_b,
    )

    assert patch_resp.status_code == 403
    assert patch_resp.json()["detail"] == "Forbidden."
    assert delete_resp.status_code == 403
    assert delete_resp.json()["detail"] == "Forbidden."


# ---------------------------------------------------------------------------
# Certifications
# ---------------------------------------------------------------------------


async def test_certifications_list_is_empty_for_cross_user(client, db) -> None:
    user_a = await _make_user(db, "a-cert-list@ownership.test")
    user_b = await _make_user(db, "b-cert-list@ownership.test")
    profile_a = await _make_profile(db, user_a.id)

    db.add(Certification(id=uuid.uuid4(), profile_id=profile_a.id, name="AWS CDA"))
    await db.flush()

    headers_b = await _login(client, user_b.email, _PASSWORD)
    response = await client.get("/api/v1/profile/certifications", headers=headers_b)

    assert response.status_code == 200
    assert response.json() == []


async def test_certifications_patch_and_delete_cross_user_return_403(client, db) -> None:
    user_a = await _make_user(db, "a-cert-mut@ownership.test")
    user_b = await _make_user(db, "b-cert-mut@ownership.test")
    profile_a = await _make_profile(db, user_a.id)

    cert = Certification(id=uuid.uuid4(), profile_id=profile_a.id, name="AWS CDA")
    db.add(cert)
    await db.flush()

    headers_b = await _login(client, user_b.email, _PASSWORD)

    patch_resp = await client.patch(
        f"/api/v1/profile/certifications/{cert.id}",
        headers=headers_b,
        json={"issuer": "Intruder Inc"},
    )
    delete_resp = await client.delete(
        f"/api/v1/profile/certifications/{cert.id}",
        headers=headers_b,
    )

    assert patch_resp.status_code == 403
    assert patch_resp.json()["detail"] == "Forbidden."
    assert delete_resp.status_code == 403
    assert delete_resp.json()["detail"] == "Forbidden."


# ---------------------------------------------------------------------------
# Resumes
# ---------------------------------------------------------------------------


async def test_resume_get_cross_user_returns_404(client, db) -> None:
    user_a = await _make_user(db, "a-resume@ownership.test")
    user_b = await _make_user(db, "b-resume@ownership.test")

    resume = Resume(id=uuid.uuid4(), user_id=user_a.id)
    db.add(resume)
    await db.flush()

    headers_b = await _login(client, user_b.email, _PASSWORD)
    response = await client.get(f"/api/v1/resumes/{resume.id}", headers=headers_b)

    assert response.status_code == 404
    assert response.json()["detail"] == "Resume not found."


# ---------------------------------------------------------------------------
# Resume versions
# ---------------------------------------------------------------------------


async def test_resume_version_get_cross_user_returns_404(client, db) -> None:
    user_a = await _make_user(db, "a-ver@ownership.test")
    user_b = await _make_user(db, "b-ver@ownership.test")

    resume = Resume(id=uuid.uuid4(), user_id=user_a.id)
    db.add(resume)
    await db.flush()

    version = ResumeVersion(id=uuid.uuid4(), resume_id=resume.id)
    db.add(version)
    await db.flush()

    headers_b = await _login(client, user_b.email, _PASSWORD)
    response = await client.get(
        f"/api/v1/resumes/versions/{version.id}", headers=headers_b
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Version not found."


# ---------------------------------------------------------------------------
# Resume bullets
# ---------------------------------------------------------------------------


async def test_resume_bullet_approve_and_delete_cross_user_return_404(
    client, db
) -> None:
    user_a = await _make_user(db, "a-bullet@ownership.test")
    user_b = await _make_user(db, "b-bullet@ownership.test")

    resume = Resume(id=uuid.uuid4(), user_id=user_a.id)
    db.add(resume)
    await db.flush()

    bullet = ResumeBullet(
        id=uuid.uuid4(),
        resume_id=resume.id,
        text="Built scalable APIs with FastAPI.",
        is_ai_generated=True,
        is_approved=False,
    )
    db.add(bullet)
    await db.flush()

    headers_b = await _login(client, user_b.email, _PASSWORD)

    approve_resp = await client.patch(
        f"/api/v1/resumes/{resume.id}/bullets/{bullet.id}/approve",
        headers=headers_b,
    )
    delete_resp = await client.delete(
        f"/api/v1/resumes/{resume.id}/bullets/{bullet.id}",
        headers=headers_b,
    )

    assert approve_resp.status_code == 404
    assert approve_resp.json()["detail"] == "Bullet not found."
    assert delete_resp.status_code == 404
    assert delete_resp.json()["detail"] == "Bullet not found."
