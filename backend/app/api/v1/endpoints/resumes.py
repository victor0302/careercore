"""Resume endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dependencies import get_ai_provider
from app.ai.exceptions import BudgetExceededError
from app.ai.provider import AIProvider
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.resume import (
    BulletsGenerateRequest,
    ResumeBulletRead,
    ResumeCreate,
    ResumeRead,
)
from app.services.resume_service import ResumeService

router = APIRouter()


@router.get("", response_model=list[ResumeRead])
async def list_resumes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
) -> list[ResumeRead]:
    """List all resumes for the authenticated user."""
    service = ResumeService(db, ai)
    resumes = await service.list_for_user(current_user.id)
    return [ResumeRead.model_validate(r) for r in resumes]


@router.post("", response_model=ResumeRead, status_code=status.HTTP_201_CREATED)
async def create_resume(
    data: ResumeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
) -> ResumeRead:
    """Create a new resume, optionally tied to a job description."""
    service = ResumeService(db, ai)
    resume = await service.create(current_user.id, data)
    return ResumeRead.model_validate(resume)


@router.get("/{resume_id}", response_model=ResumeRead)
async def get_resume(
    resume_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
) -> ResumeRead:
    """Get a resume by ID. Enforces ownership."""
    service = ResumeService(db, ai)
    resume = await service.get_for_user(current_user.id, resume_id)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found.")
    return ResumeRead.model_validate(resume)


@router.post("/{resume_id}/bullets/generate", response_model=list[ResumeBulletRead])
async def generate_bullets(
    resume_id: uuid.UUID,
    data: BulletsGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
) -> list[ResumeBulletRead]:
    """Generate AI resume bullets for a resume."""
    service = ResumeService(db, ai)
    try:
        bullets = await service.generate_bullets(
            current_user,
            resume_id,
            data.profile_entity_type,
            data.profile_entity_id,
            data.requirement_ids,
        )
    except BudgetExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "message": "Daily AI token budget exceeded.",
                "reset_at": exc.reset_at.isoformat(),
            },
        ) from exc
    except ValueError as exc:
        detail = str(exc)
        not_found_messages = {
            "Resume not found.",
            "Work experience not found.",
            "Project not found.",
        }
        status_code = (
            status.HTTP_404_NOT_FOUND
            if detail in not_found_messages
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc

    return [ResumeBulletRead.model_validate(bullet) for bullet in bullets]
