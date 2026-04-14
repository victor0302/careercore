"""Certification endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.certification import Certification
from app.models.user import User
from app.schemas.profile import CertificationCreate, CertificationRead, CertificationUpdate
from app.services.profile_service import ProfileService

router = APIRouter()


@router.get("", response_model=list[CertificationRead])
async def list_certifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CertificationRead]:
    certifications = await ProfileService(db).list_child_entities_for_user(
        Certification,
        current_user.id,
    )
    return [CertificationRead.model_validate(c) for c in certifications]


@router.post("", response_model=CertificationRead, status_code=status.HTTP_201_CREATED)
async def create_certification(
    data: CertificationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CertificationRead:
    profile_service = ProfileService(db)
    profile = await profile_service.get_or_create(current_user.id)
    cert = Certification(profile_id=profile.id, **data.model_dump())
    db.add(cert)
    await db.flush()
    await profile_service.recalculate_completeness(profile)
    return CertificationRead.model_validate(cert)


@router.patch("/{cert_id}", response_model=CertificationRead)
async def update_certification(
    cert_id: uuid.UUID,
    data: CertificationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CertificationRead:
    profile_service = ProfileService(db)
    cert, exists_elsewhere = await profile_service.get_child_entity_access(
        Certification,
        current_user.id,
        cert_id,
    )
    if cert is None:
        if exists_elsewhere:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certification not found.")
    profile = await profile_service.get_or_create(current_user.id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(cert, field, value)
    await db.flush()
    await profile_service.recalculate_completeness(profile)
    return CertificationRead.model_validate(cert)


@router.delete("/{cert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certification(
    cert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    profile_service = ProfileService(db)
    cert, exists_elsewhere = await profile_service.get_child_entity_access(
        Certification,
        current_user.id,
        cert_id,
    )
    if cert is None:
        if exists_elsewhere:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certification not found.")
    profile = await profile_service.get_or_create(current_user.id)
    await db.delete(cert)
    await db.flush()
    await profile_service.recalculate_completeness(profile)
