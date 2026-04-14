from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.ai.exceptions import BudgetExceededError
from app.ai.providers.mock_provider import MockAIProvider
from app.models.ai_call_log import AICallLog, AICallType
from app.models.job_description import JobDescription
from app.models.job_requirement import JobRequirement
from app.services.job_service import JobService


async def test_parse_persists_requirements_and_logs_ai_call(db, mock_user) -> None:
    job = JobDescription(
        user_id=mock_user.id,
        title="Backend Engineer",
        company="CareerCore",
        raw_text="Need Python, FastAPI or Django, and Docker familiarity.",
    )
    db.add(job)
    await db.flush()

    service = JobService(db, MockAIProvider())
    parsed_job = await service.parse(mock_user.id, job.id)

    assert parsed_job.parsed_at is not None

    requirement_result = await db.execute(
        select(JobRequirement).where(JobRequirement.job_id == job.id).order_by(JobRequirement.id)
    )
    requirements = list(requirement_result.scalars())
    assert len(requirements) == 3
    assert [(req.text, req.category, req.is_required) for req in requirements] == [
        ("3+ years of Python experience", "skill", True),
        ("Experience with FastAPI or Django", "tool", True),
        ("Familiarity with Docker", "tool", False),
    ]

    log_result = await db.execute(
        select(AICallLog).where(
            AICallLog.user_id == mock_user.id,
            AICallLog.call_type == AICallType.parse_job_description,
        )
    )
    logs = list(log_result.scalars())
    assert len(logs) == 1
    assert logs[0].model == "mock"
    assert logs[0].prompt_tokens == 0
    assert logs[0].completion_tokens == 0
    assert logs[0].total_tokens == 0
    assert logs[0].cost_usd == Decimal("0")
    assert logs[0].success is True
    assert logs[0].error_message is None


async def test_parse_checks_budget_before_provider_call(db, mock_user) -> None:
    job = JobDescription(
        user_id=mock_user.id,
        title="Backend Engineer",
        company="CareerCore",
        raw_text="Need Python, FastAPI or Django, and Docker familiarity.",
    )
    db.add(job)
    db.add(
        AICallLog(
            user_id=mock_user.id,
            call_type=AICallType.parse_job_description,
            model="mock",
            prompt_tokens=50_000,
            completion_tokens=0,
            total_tokens=50_000,
            cost_usd=Decimal("0.050000"),
            latency_ms=1,
            success=True,
            error_message=None,
            created_at=datetime.now(tz=timezone.utc),
        )
    )
    await db.flush()

    service = JobService(db, MockAIProvider())
    with pytest.raises(BudgetExceededError):
        await service.parse(mock_user.id, job.id)

    requirement_result = await db.execute(
        select(JobRequirement).where(JobRequirement.job_id == job.id)
    )
    assert list(requirement_result.scalars()) == []

    await db.refresh(job)
    assert job.parsed_at is None
