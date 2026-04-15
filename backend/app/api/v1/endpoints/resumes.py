"""Resume endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dependencies import get_ai_provider
from app.ai.provider import AIProvider
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.resume import ResumeBulletRead, ResumeCreate, ResumeRead
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


@router.post("/{resume_id}/bullets/generate")
async def generate_bullets(
    resume_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
) -> dict:  # type: ignore[type-arg]
    """Generate AI resume bullets for a resume. TODO: implement in Phase 1."""
    return {"status": "not implemented", "message": "Phase 1 — implement generate_bullets"}


@router.patch("/{resume_id}/bullets/{bullet_id}/approve", response_model=ResumeBulletRead)
async def approve_bullet(
    resume_id: uuid.UUID,
    bullet_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
) -> ResumeBulletRead:
    """Approve an AI-generated resume bullet."""
    service = ResumeService(db, ai)
    bullet = await service.approve_bullet(current_user.id, resume_id, bullet_id)
    if bullet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bullet not found.")
    return ResumeBulletRead.model_validate(bullet)


@router.delete("/{resume_id}/bullets/{bullet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def reject_bullet(
    resume_id: uuid.UUID,
    bullet_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
) -> Response:
    """Reject and delete an AI-generated resume bullet."""
    service = ResumeService(db, ai)
    deleted = await service.reject_bullet(current_user.id, resume_id, bullet_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bullet not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
