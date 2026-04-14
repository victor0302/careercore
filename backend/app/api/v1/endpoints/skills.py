"""Skill endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.skill import Skill
from app.models.user import User
from app.schemas.profile import SkillCreate, SkillRead, SkillUpdate
from app.services.profile_service import ProfileService

router = APIRouter()


@router.get("", response_model=list[SkillRead])
async def list_skills(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SkillRead]:
    skills = await ProfileService(db).list_child_entities_for_user(Skill, current_user.id)
    return [SkillRead.model_validate(s) for s in skills]


@router.post("", response_model=SkillRead, status_code=status.HTTP_201_CREATED)
async def create_skill(
    data: SkillCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillRead:
    profile_service = ProfileService(db)
    profile = await profile_service.get_or_create(current_user.id)
    skill = Skill(profile_id=profile.id, **data.model_dump())
    db.add(skill)
    await db.flush()
    await profile_service.recalculate_completeness(profile)
    return SkillRead.model_validate(skill)


@router.patch("/{skill_id}", response_model=SkillRead)
async def update_skill(
    skill_id: uuid.UUID,
    data: SkillUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillRead:
    profile_service = ProfileService(db)
    skill, exists_elsewhere = await profile_service.get_child_entity_access(
        Skill,
        current_user.id,
        skill_id,
    )
    if skill is None:
        if exists_elsewhere:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found.")
    profile = await profile_service.get_or_create(current_user.id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(skill, field, value)
    await db.flush()
    await profile_service.recalculate_completeness(profile)
    return SkillRead.model_validate(skill)


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    profile_service = ProfileService(db)
    skill, exists_elsewhere = await profile_service.get_child_entity_access(
        Skill,
        current_user.id,
        skill_id,
    )
    if skill is None:
        if exists_elsewhere:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found.")
    profile = await profile_service.get_or_create(current_user.id)
    await db.delete(skill)
    await db.flush()
    await profile_service.recalculate_completeness(profile)
