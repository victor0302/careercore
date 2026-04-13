"""Profile service — create and manage the user's master career profile."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.profile import Profile
from app.schemas.profile import ProfileUpdate


class ProfileService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_or_create(self, user_id: uuid.UUID) -> Profile:
        """Return the profile for a user, creating it if it does not exist.

        TODO: After creation, trigger a completeness_pct recalculation.
        """
        result = await self._db.execute(
            select(Profile)
            .where(Profile.user_id == user_id)
            .options(
                selectinload(Profile.work_experiences),
                selectinload(Profile.projects),
                selectinload(Profile.skills),
                selectinload(Profile.certifications),
            )
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            profile = Profile(user_id=user_id)
            self._db.add(profile)
            await self._db.flush()
        return profile

    async def update(self, user_id: uuid.UUID, data: ProfileUpdate) -> Profile:
        """Apply partial updates to the user's profile.

        TODO: After update, recalculate completeness_pct and save.
        """
        profile = await self.get_or_create(user_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(profile, field, value)
        await self._db.flush()
        return profile

    async def recalculate_completeness(self, profile: Profile) -> float:
        """Compute and persist the profile completeness percentage.

        Scoring rubric (Phase 1):
          - display_name set: 10 pts
          - current_title set: 10 pts
          - target_domain set: 10 pts
          - At least 1 work experience: 25 pts
          - At least 1 skill: 20 pts
          - At least 1 project: 15 pts
          - At least 1 certification: 10 pts

        TODO: Implement this calculation and call it whenever child entities change.
        """
        # Placeholder — returns 0 until implemented
        return 0.0
