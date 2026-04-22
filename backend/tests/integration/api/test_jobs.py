import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import select

from app.models.job_analysis import JobAnalysis, MatchType, MatchedRequirement, MissingRequirement
from app.core.security import hash_password
from app.models.job_description import JobDescription
from app.models.job_requirement import JobRequirement, JobRequirementCategory
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


async def test_job_list_includes_latest_fit_score_when_present(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    analyzed_job = JobDescription(
        user_id=mock_user.id,
        title="Analyzed Job",
        company="CareerCore",
        raw_text="Ship backend systems.",
    )
    unanalyzed_job = JobDescription(
        user_id=mock_user.id,
        title="Unanalyzed Job",
        company="CareerCore",
        raw_text="Support internal tools.",
    )
    db.add_all([analyzed_job, unanalyzed_job])
    await db.flush()

    older_analysis = JobAnalysis(
        job_id=analyzed_job.id,
        user_id=mock_user.id,
        fit_score=61.0,
        score_breakdown={"total_score": 61.0},
        analyzed_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
    )
    latest_analysis = JobAnalysis(
        job_id=analyzed_job.id,
        user_id=mock_user.id,
        fit_score=88.0,
        score_breakdown={"total_score": 88.0},
        analyzed_at=datetime(2026, 4, 14, 13, 0, tzinfo=timezone.utc),
    )
    db.add_all([older_analysis, latest_analysis])
    await db.flush()

    response = await client.get("/api/v1/jobs", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    by_id = {job["id"]: job for job in payload}

    assert by_id[str(analyzed_job.id)]["latest_analysis"] == {
        "id": str(latest_analysis.id),
        "fit_score": 88.0,
        "analyzed_at": "2026-04-14T13:00:00Z",
    }
    assert by_id[str(unanalyzed_job.id)]["latest_analysis"] is None


async def test_job_detail_includes_latest_analysis_evidence_and_requirements(
    client, mock_user, db
) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    other_user = User(
        id=uuid.uuid4(),
        email="analysis-owner@careercore.test",
        password_hash=hash_password("Otherpassword123"),
        is_active=True,
    )
    db.add(other_user)
    await db.flush()

    job = JobDescription(
        user_id=mock_user.id,
        title="Staff Backend Engineer",
        company="CareerCore",
        raw_text="Lead backend platform work.",
    )
    db.add(job)
    await db.flush()

    matched_requirement = JobRequirement(
        job_id=job.id,
        requirement_text="Python backend experience",
        category=JobRequirementCategory.skill,
        is_required=True,
    )
    missing_requirement = JobRequirement(
        job_id=job.id,
        requirement_text="Kubernetes operations",
        category=JobRequirementCategory.tool,
        is_required=True,
    )
    db.add_all([matched_requirement, missing_requirement])
    await db.flush()

    analysis = JobAnalysis(
        job_id=job.id,
        user_id=mock_user.id,
        fit_score=84.0,
        score_breakdown={
            "total_score": 84.0,
            "matched": [{"requirement_id": str(matched_requirement.id)}],
            "missing": [{"requirement_id": str(missing_requirement.id)}],
            "evidence_map": {
                str(matched_requirement.id): [
                    {
                        "source_entity_type": "project",
                        "source_entity_id": str(uuid.uuid4()),
                        "confidence": 0.91,
                    }
                ]
            },
        },
        analyzed_at=datetime(2026, 4, 14, 14, 30, tzinfo=timezone.utc),
    )
    db.add(analysis)
    await db.flush()

    foreign_analysis = JobAnalysis(
        job_id=job.id,
        user_id=other_user.id,
        fit_score=99.0,
        score_breakdown={"total_score": 99.0, "evidence_map": {"leak": []}},
        analyzed_at=datetime(2026, 4, 14, 15, 0, tzinfo=timezone.utc),
    )
    db.add(foreign_analysis)
    await db.flush()

    matched_row = MatchedRequirement(
        analysis_id=analysis.id,
        requirement_id=matched_requirement.id,
        match_type=MatchType.full,
        source_entity_type="project",
        source_entity_id=uuid.uuid4(),
        confidence=0.91,
    )
    missing_row = MissingRequirement(
        analysis_id=analysis.id,
        requirement_id=missing_requirement.id,
        suggested_action="Build one production deployment project using Kubernetes.",
    )
    db.add_all([matched_row, missing_row])
    await db.flush()

    response = await client.get(f"/api/v1/jobs/{job.id}", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    latest_analysis = payload["latest_analysis"]
    assert latest_analysis["id"] == str(analysis.id)
    assert latest_analysis["fit_score"] == 84.0
    assert latest_analysis["score_breakdown"]["total_score"] == 84.0
    assert latest_analysis["evidence_map"] == analysis.score_breakdown["evidence_map"]
    assert latest_analysis["matched_requirements"] == [
        {
            "id": str(matched_row.id),
            "requirement_id": str(matched_requirement.id),
            "match_type": "full",
            "source_entity_type": "project",
            "source_entity_id": str(matched_row.source_entity_id),
            "confidence": 0.91,
        }
    ]
    assert latest_analysis["missing_requirements"] == [
        {
            "id": str(missing_row.id),
            "requirement_id": str(missing_requirement.id),
            "suggested_action": "Build one production deployment project using Kubernetes.",
        }
    ]


async def test_create_job_enqueues_celery_parse_task(client, mock_user, db) -> None:
    headers = await _login(client, mock_user.email, "testpassword123")

    with patch("app.workers.tasks.job_tasks.parse_job.delay") as mock_delay:
        response = await client.post(
            "/api/v1/jobs",
            headers=headers,
            json={
                "title": "Backend Engineer",
                "company": "Acme",
                "raw_text": "Build and scale backend services.",
            },
        )

    assert response.status_code == 201
    payload = response.json()
    job_id = payload["id"]
    user_id = str(mock_user.id)

    mock_delay.assert_called_once_with(job_id, user_id)
