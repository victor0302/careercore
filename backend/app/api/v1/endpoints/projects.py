"""Project endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.profile import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.profile_service import ProfileService

router = APIRouter()


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectRead]:
    projects = await ProfileService(db).list_child_entities_for_user(Project, current_user.id)
    return [ProjectRead.model_validate(p) for p in projects]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectRead:
    profile_service = ProfileService(db)
    profile = await profile_service.get_or_create(current_user.id)
    proj = Project(profile_id=profile.id, **data.model_dump())
    db.add(proj)
    await db.flush()
    await profile_service.recalculate_completeness(profile)
    return ProjectRead.model_validate(proj)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectRead:
    profile_service = ProfileService(db)
    proj, exists_elsewhere = await profile_service.get_child_entity_access(
        Project,
        current_user.id,
        project_id,
    )
    if proj is None:
        if exists_elsewhere:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    profile = await profile_service.get_or_create(current_user.id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(proj, field, value)
    await db.flush()
    await profile_service.recalculate_completeness(profile)
    return ProjectRead.model_validate(proj)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    profile_service = ProfileService(db)
    proj, exists_elsewhere = await profile_service.get_child_entity_access(
        Project,
        current_user.id,
        project_id,
    )
    if proj is None:
        if exists_elsewhere:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    profile = await profile_service.get_or_create(current_user.id)
    await db.delete(proj)
    await db.flush()
    await profile_service.recalculate_completeness(profile)
