"""Profile service — create and manage the user's master career profile."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.certification import Certification
from app.models.profile import Profile
from app.models.project import Project
from app.models.skill import Skill
from app.models.work_experience import WorkExperience
from app.schemas.profile import ProfileUpdate


class ProfileService:
    _FIELD_WEIGHTS = {
        "display_name": 0.10,
        "current_title": 0.10,
        "target_domain": 0.10,
    }
    _SECTION_WEIGHTS = {
        WorkExperience: 0.25,
        Skill: 0.20,
        Project: 0.15,
        Certification: 0.10,
    }

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
            await self.recalculate_completeness(profile)
        return profile

    async def update(self, user_id: uuid.UUID, data: ProfileUpdate) -> Profile:
        """Apply partial updates to the user's profile.

        TODO: After update, recalculate completeness_pct and save.
        """
        profile = await self.get_or_create(user_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(profile, field, value)
        await self.recalculate_completeness(profile)
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
        section_presence = {
            model: await self._has_related_rows(model, profile.id)
            for model in self._SECTION_WEIGHTS
        }
        score = self._calculate_completeness_score(profile, section_presence)
        profile.completeness_pct = score
        await self._db.flush()
        return score

    @classmethod
    def _calculate_completeness_score(
        cls, profile: object, section_presence: dict[type, bool]
    ) -> float:
        score = 0.0

        for field, weight in cls._FIELD_WEIGHTS.items():
            value = getattr(profile, field)
            if isinstance(value, str) and value.strip():
                score += weight

        for model, weight in cls._SECTION_WEIGHTS.items():
            if section_presence.get(model, False):
                score += weight

        return score

    async def _has_related_rows(self, model: type, profile_id: uuid.UUID) -> bool:
        result = await self._db.execute(select(model.id).where(model.profile_id == profile_id).limit(1))
        return result.scalar_one_or_none() is not None
