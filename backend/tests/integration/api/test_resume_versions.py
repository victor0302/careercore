import uuid
from datetime import date, datetime, timedelta, timezone

from app.core.security import hash_password
from app.models.job_description import JobDescription
from app.models.profile import Profile
from app.models.project import Project
from app.models.resume import EvidenceLink, Resume, ResumeBullet, ResumeVersion
from app.models.user import User
from app.models.work_experience import WorkExperience


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


async def test_resume_version_detail_resolves_evidence_display_names(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    profile = Profile(id=uuid.uuid4(), user_id=mock_user.id, completeness_pct=0.0)
    job = JobDescription(
        user_id=mock_user.id,
        title="Backend Engineer",
        company="CareerCore",
        raw_text="Build APIs.",
    )
    resume = Resume(user_id=mock_user.id, job=job)
    db.add_all([profile, job, resume])
    await db.flush()

    work_experience = WorkExperience(
        profile_id=profile.id,
        employer="Acme",
        role_title="Platform Engineer",
        start_date=date(2020, 1, 1),
        end_date=None,
        is_current=True,
        description_raw="Built internal systems.",
    )
    project = Project(
        profile_id=profile.id,
        name="CareerCore",
        description_raw="Job-fit product.",
        url="https://example.com",
    )
    db.add_all([work_experience, project])
    await db.flush()

    version = ResumeVersion(
        resume_id=resume.id,
        fit_score_at_gen=87.0,
        created_at=datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
    )
    approved_bullet = ResumeBullet(
        resume_id=resume.id,
        text="Improved platform reliability and shipped product features.",
        is_ai_generated=True,
        is_approved=True,
        confidence=0.91,
    )
    unapproved_bullet = ResumeBullet(
        resume_id=resume.id,
        text="Draft bullet that should not appear.",
        is_ai_generated=True,
        is_approved=False,
        confidence=0.40,
    )
    db.add_all([version, approved_bullet, unapproved_bullet])
    await db.flush()

    db.add_all(
        [
            EvidenceLink(
                bullet_id=approved_bullet.id,
                source_entity_type="work_experience",
                source_entity_id=work_experience.id,
            ),
            EvidenceLink(
                bullet_id=approved_bullet.id,
                source_entity_type="project",
                source_entity_id=project.id,
            ),
            EvidenceLink(
                bullet_id=unapproved_bullet.id,
                source_entity_type="project",
                source_entity_id=project.id,
            ),
        ]
    )
    await db.flush()

    response = await client.get(f"/api/v1/resumes/versions/{version.id}", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(version.id)
    assert payload["resume_id"] == str(resume.id)
    assert payload["fit_score_at_gen"] == 87.0
    assert payload["created_at"] == "2026-04-15T12:00:00Z"
    assert payload["job_title"] == "Backend Engineer"
    assert payload["job_company"] == "CareerCore"

    assert len(payload["bullets"]) == 1
    bullet = payload["bullets"][0]
    assert bullet["id"] == str(approved_bullet.id)
    assert bullet["text"] == "Improved platform reliability and shipped product features."
    assert bullet["confidence"] == 0.91

    evidence_by_type = {item["source_entity_type"]: item for item in bullet["evidence"]}
    assert evidence_by_type["work_experience"]["source_entity_id"] == str(work_experience.id)
    assert evidence_by_type["work_experience"]["display_name"] == "Platform Engineer at Acme"
    assert evidence_by_type["project"]["source_entity_id"] == str(project.id)
    assert evidence_by_type["project"]["display_name"] == "CareerCore"


async def test_resume_version_detail_returns_404_for_other_users_version(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    other_user = User(
        id=uuid.uuid4(),
        email="other-version-owner@careercore.test",
        password_hash=hash_password("Otherpassword123"),
        is_active=True,
    )
    other_resume = Resume(user_id=other_user.id, job_id=None)
    db.add_all([other_user, other_resume])
    await db.flush()

    version = ResumeVersion(resume_id=other_resume.id, fit_score_at_gen=75.0)
    db.add(version)
    await db.flush()

    response = await client.get(f"/api/v1/resumes/versions/{version.id}", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Version not found."


async def test_resume_version_detail_excludes_unapproved_bullets(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    resume = Resume(user_id=mock_user.id, job_id=None)
    db.add(resume)
    await db.flush()

    version = ResumeVersion(resume_id=resume.id, fit_score_at_gen=62.0)
    approved_bullet = ResumeBullet(
        resume_id=resume.id,
        text="Approved bullet.",
        is_ai_generated=False,
        is_approved=True,
        confidence=None,
    )
    unapproved_bullet = ResumeBullet(
        resume_id=resume.id,
        text="Unapproved bullet.",
        is_ai_generated=False,
        is_approved=False,
        confidence=None,
    )
    db.add_all([version, approved_bullet, unapproved_bullet])
    await db.flush()

    response = await client.get(f"/api/v1/resumes/versions/{version.id}", headers=headers)

    assert response.status_code == 200
    assert [bullet["text"] for bullet in response.json()["bullets"]] == ["Approved bullet."]


async def test_resume_version_detail_returns_null_job_metadata_when_resume_has_no_job(
    client, mock_user, db
) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    resume = Resume(user_id=mock_user.id, job_id=None)
    version = ResumeVersion(resume=resume, fit_score_at_gen=None)
    approved_bullet = ResumeBullet(
        resume=resume,
        text="Bullet without linked job.",
        is_ai_generated=False,
        is_approved=True,
        confidence=0.5,
    )
    db.add_all([resume, version, approved_bullet])
    await db.flush()

    response = await client.get(f"/api/v1/resumes/versions/{version.id}", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_title"] is None
    assert payload["job_company"] is None
