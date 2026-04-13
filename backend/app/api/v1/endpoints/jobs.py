"""Job description endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dependencies import get_ai_provider
from app.ai.provider import AIProvider
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.job import JobDescriptionCreate, JobDescriptionRead
from app.services.job_service import JobService

router = APIRouter()


@router.get("", response_model=list[JobDescriptionRead])
async def list_jobs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
) -> list[JobDescriptionRead]:
    """List all job descriptions for the authenticated user."""
    service = JobService(db, ai)
    jobs = await service.list_for_user(current_user.id)
    return [JobDescriptionRead.model_validate(j) for j in jobs]


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


@router.get("/{job_id}", response_model=JobDescriptionRead)
async def get_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
) -> JobDescriptionRead:
    """Get a single job description by ID."""
    service = JobService(db, ai)
    job = await service.get_for_user(current_user.id, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return JobDescriptionRead.model_validate(job)


@router.post("/{job_id}/parse", response_model=JobDescriptionRead)
async def parse_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
) -> JobDescriptionRead:
    """Trigger AI parsing of a job description.

    TODO: Wire up AICostService budget check before parsing.
    """
    service = JobService(db, ai)
    try:
        job = await service.parse(current_user.id, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return JobDescriptionRead.model_validate(job)
