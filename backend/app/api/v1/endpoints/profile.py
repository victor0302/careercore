"""Profile endpoints — get and update the authenticated user's master profile."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.profile import ProfileRead, ProfileUpdate
from app.services.profile_service import ProfileService

router = APIRouter()


@router.get("", response_model=ProfileRead)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileRead:
    """Return the authenticated user's profile, creating it if it does not exist."""
    service = ProfileService(db)
    profile = await service.get_or_create(current_user.id)
    return ProfileRead.model_validate(profile)


@router.patch("", response_model=ProfileRead)
async def update_profile(
    data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileRead:
    """Partially update the authenticated user's profile."""
    service = ProfileService(db)
    profile = await service.update(current_user.id, data)
    return ProfileRead.model_validate(profile)
