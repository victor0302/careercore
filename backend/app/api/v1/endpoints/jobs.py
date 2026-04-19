"""Job description endpoints."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dependencies import get_ai_provider
from app.ai.exceptions import BudgetExceededError
from app.ai.provider import AIProvider
from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.core.rate_limit import AIRateLimiter
from app.db.session import get_db
from app.models.job_analysis import JobAnalysis
from app.models.job_description import JobDescription
from app.models.user import User
from app.schemas.job import (
    JobAnalysisDetailRead,
    JobAnalysisSummaryRead,
    JobDescriptionCreate,
    JobDescriptionRead,
    JobDetailRead,
    JobListRead,
    MatchedRequirementRead,
    MissingRequirementRead,
)
from app.services.job_service import JobService

router = APIRouter()

_settings = get_settings()
_parse_rate_limiter = AIRateLimiter(
    endpoint_name="analyze",
    max_requests=_settings.AI_ANALYZE_RATE_LIMIT_REQUESTS,
    window_seconds=_settings.AI_ANALYZE_RATE_LIMIT_WINDOW_SECONDS,
)


def _serialize_analysis_summary(analysis: JobAnalysis) -> JobAnalysisSummaryRead:
    return JobAnalysisSummaryRead.model_validate(analysis)


def _serialize_analysis_detail(analysis: JobAnalysis) -> JobAnalysisDetailRead:
    score_breakdown: dict[str, Any] = dict(analysis.score_breakdown or {})
    evidence_map = score_breakdown.get("evidence_map")
    if not isinstance(evidence_map, dict):
        evidence_map = {}

    return JobAnalysisDetailRead(
        id=analysis.id,
        fit_score=analysis.fit_score,
        analyzed_at=analysis.analyzed_at,
        score_breakdown=score_breakdown,
        evidence_map=evidence_map,
        matched_requirements=[
            MatchedRequirementRead.model_validate(item) for item in analysis.matched_requirements
        ],
        missing_requirements=[
            MissingRequirementRead.model_validate(item) for item in analysis.missing_requirements
        ],
    )


def _serialize_job_list(job: JobDescription, latest_analysis: JobAnalysis | None) -> JobListRead:
    return JobListRead(
        id=job.id,
        user_id=job.user_id,
        title=job.title,
        company=job.company,
        raw_text=job.raw_text,
        parsed_at=job.parsed_at,
        latest_analysis=(
            _serialize_analysis_summary(latest_analysis) if latest_analysis is not None else None
        ),
    )


def _serialize_job_detail(job: JobDescription, latest_analysis: JobAnalysis | None) -> JobDetailRead:
    return JobDetailRead(
        id=job.id,
        user_id=job.user_id,
        title=job.title,
        company=job.company,
        raw_text=job.raw_text,
        parsed_at=job.parsed_at,
        latest_analysis=(
            _serialize_analysis_detail(latest_analysis) if latest_analysis is not None else None
        ),
    )


@router.get("", response_model=list[JobListRead])
async def list_jobs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
) -> list[JobListRead]:
    """List all job descriptions for the authenticated user."""
    service = JobService(db, ai)
    jobs = await service.list_for_user(current_user.id)
    return [
        _serialize_job_list(job, service.get_latest_analysis(job, current_user.id))
        for job in jobs
    ]


@router.post("", response_model=JobDescriptionRead, status_code=status.HTTP_201_CREATED)
async def create_job(
    data: JobDescriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
) -> JobDescriptionRead:
    """Submit a new job description for parsing and analysis."""
    service = JobService(db, ai)
    job = await service.create(current_user.id, data)
    return JobDescriptionRead.model_validate(job)


@router.get("/{job_id}", response_model=JobDetailRead)
async def get_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
) -> JobDetailRead:
    """Get a single job description by ID."""
    service = JobService(db, ai)
    job = await service.get_for_user(current_user.id, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return _serialize_job_detail(job, service.get_latest_analysis(job, current_user.id))


@router.post("/{job_id}/parse", response_model=JobDescriptionRead)
async def parse_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
    _rl: None = Depends(_parse_rate_limiter),
) -> JobDescriptionRead:
    """Trigger AI parsing of a job description.

    TODO: Wire up AICostService budget check before parsing.
    """
    service = JobService(db, ai)
    try:
        job = await service.parse(current_user.id, job_id)
    except BudgetExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily AI token budget exceeded.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return JobDescriptionRead.model_validate(job)
