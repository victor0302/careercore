import os
import uuid
from types import SimpleNamespace
from datetime import datetime, timezone

os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("MINIO_BUCKET", "careercore-test")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

from app.api.v1.endpoints.jobs import _serialize_job_detail, _serialize_job_list
from app.services.job_service import JobService


def test_latest_analysis_ignores_other_users_and_serializes_detail() -> None:
    owner_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    requirement_id = uuid.uuid4()
    source_entity_id = uuid.uuid4()

    job_id = uuid.uuid4()
    owned_analysis = SimpleNamespace(
        id=uuid.uuid4(),
        job_id=job_id,
        user_id=owner_id,
        fit_score=82.0,
        score_breakdown={
            "total_score": 82.0,
            "evidence_map": {
                str(requirement_id): [
                    {
                        "source_entity_type": "project",
                        "source_entity_id": str(source_entity_id),
                        "confidence": 0.93,
                    }
                ]
            },
        },
        analyzed_at=datetime(2026, 4, 14, 18, 0, tzinfo=timezone.utc),
    )
    foreign_analysis = SimpleNamespace(
        id=uuid.uuid4(),
        job_id=job_id,
        user_id=other_user_id,
        fit_score=99.0,
        score_breakdown={"total_score": 99.0, "evidence_map": {"leak": []}},
        analyzed_at=datetime(2026, 4, 14, 19, 0, tzinfo=timezone.utc),
    )
    owned_analysis.matched_requirements = [
        SimpleNamespace(
            id=uuid.uuid4(),
            analysis_id=owned_analysis.id,
            requirement_id=requirement_id,
            match_type="full",
            source_entity_type="project",
            source_entity_id=source_entity_id,
            confidence=0.93,
        )
    ]
    owned_analysis.missing_requirements = [
        SimpleNamespace(
            id=uuid.uuid4(),
            analysis_id=owned_analysis.id,
            requirement_id=uuid.uuid4(),
            suggested_action="Add a deployment-focused project example.",
        )
    ]
    job = SimpleNamespace(
        id=job_id,
        user_id=owner_id,
        title="Backend Engineer",
        company="CareerCore",
        raw_text="Build APIs.",
        parsed_at=None,
        analyses=[owned_analysis, foreign_analysis],
    )

    latest_analysis = JobService.get_latest_analysis(job, owner_id)
    list_payload = _serialize_job_list(job, latest_analysis)
    detail_payload = _serialize_job_detail(job, latest_analysis)

    assert latest_analysis is owned_analysis
    assert list_payload.latest_analysis is not None
    assert list_payload.latest_analysis.fit_score == 82.0
    assert detail_payload.latest_analysis is not None
    assert detail_payload.latest_analysis.fit_score == 82.0
    assert detail_payload.latest_analysis.evidence_map == owned_analysis.score_breakdown["evidence_map"]
    assert detail_payload.latest_analysis.matched_requirements[0].match_type == "full"
    assert (
        detail_payload.latest_analysis.missing_requirements[0].suggested_action
        == "Add a deployment-focused project example."
    )
