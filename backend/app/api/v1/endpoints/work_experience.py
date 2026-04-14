"""Work experience endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.models.work_experience import WorkExperience
from app.schemas.profile import WorkExperienceCreate, WorkExperienceRead, WorkExperienceUpdate
from app.services.file_service import FileService
from app.services.profile_service import ProfileService

router = APIRouter()


async def _validate_source_file_ownership(
    db: AsyncSession,
    user_id: uuid.UUID,
    source_file_id: uuid.UUID | None,
) -> None:
    if source_file_id is None:
        return

    record = await FileService(db).get_for_user(user_id, source_file_id)
    if record is not None:
        return

    result = await db.execute(select(UploadedFile.id).where(UploadedFile.id == source_file_id))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found.")


@router.get("", response_model=list[WorkExperienceRead])
async def list_experiences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkExperienceRead]:
    experiences = await ProfileService(db).list_child_entities_for_user(
        WorkExperience,
        current_user.id,
    )
    return [WorkExperienceRead.model_validate(e) for e in experiences]


@router.post("", response_model=WorkExperienceRead, status_code=status.HTTP_201_CREATED)
async def create_experience(
    data: WorkExperienceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkExperienceRead:
    profile_service = ProfileService(db)
    profile = await profile_service.get_or_create(current_user.id)
    payload = data.model_dump()
    await _validate_source_file_ownership(db, current_user.id, payload.get("source_file_id"))
    exp = WorkExperience(profile_id=profile.id, **payload)
    db.add(exp)
    await db.flush()
    await profile_service.recalculate_completeness(profile)
    return WorkExperienceRead.model_validate(exp)


@router.patch("/{experience_id}", response_model=WorkExperienceRead)
async def update_experience(
    experience_id: uuid.UUID,
    data: WorkExperienceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkExperienceRead:
    profile_service = ProfileService(db)
    exp, exists_elsewhere = await profile_service.get_child_entity_access(
        WorkExperience,
        current_user.id,
        experience_id,
    )
    if exp is None:
        if exists_elsewhere:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found.")
    profile = await profile_service.get_or_create(current_user.id)
    updates = data.model_dump(exclude_unset=True)
    await _validate_source_file_ownership(db, current_user.id, updates.get("source_file_id"))
    for field, value in updates.items():
        setattr(exp, field, value)
    await db.flush()
    await profile_service.recalculate_completeness(profile)
    return WorkExperienceRead.model_validate(exp)


@router.delete("/{experience_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_experience(
    experience_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    profile_service = ProfileService(db)
    exp, exists_elsewhere = await profile_service.get_child_entity_access(
        WorkExperience,
        current_user.id,
        experience_id,
    )
    if exp is None:
        if exists_elsewhere:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found.")
    profile = await profile_service.get_or_create(current_user.id)
    await db.delete(exp)
    await db.flush()
    await profile_service.recalculate_completeness(profile)
