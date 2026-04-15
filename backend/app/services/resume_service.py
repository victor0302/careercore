"""Resume service — generate, version, and manage resumes."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import AIProvider
from app.models.resume import Resume, ResumeBullet, ResumeVersion
from app.schemas.resume import ResumeCreate


class ResumeService:
    def __init__(self, db: AsyncSession, ai_provider: AIProvider) -> None:
        self._db = db
        self._ai = ai_provider

    async def create(self, user_id: uuid.UUID, data: ResumeCreate) -> Resume:
        """Create a new empty resume for a user, optionally tied to a job.

        TODO: Validate that the job_id belongs to the user if provided.
        """
        resume = Resume(user_id=user_id, job_id=data.job_id)
        self._db.add(resume)
        await self._db.flush()
        return resume

    async def list_for_user(self, user_id: uuid.UUID) -> list[Resume]:
        """Return all resumes for a user, ordered newest first."""
        result = await self._db.execute(
            select(Resume)
            .where(Resume.user_id == user_id)
            .order_by(Resume.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_for_user(self, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume | None:
        """Return a resume, enforcing ownership."""
        result = await self._db.execute(
            select(Resume).where(
                Resume.id == resume_id,
                Resume.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def generate_bullets(
        self,
        user_id: uuid.UUID,
        resume_id: uuid.UUID,
        profile_entity_type: str,
        profile_entity_id: uuid.UUID,
        requirement_ids: list[uuid.UUID],
    ) -> list[ResumeBullet]:
        """Generate AI resume bullets for a given profile entity and job requirements.

        Steps:
          1. Validate resume ownership and retrieve the resume.
          2. Retrieve the profile entity (work experience or project).
          3. Retrieve the job requirements by requirement_ids.
          4. Check AICostService.check_budget() for the user.
          5. Build BulletContext objects.
          6. Call self._ai.generate_bullets(contexts).
          7. Persist ResumeBullet rows (is_ai_generated=True, is_approved=False).
          8. Persist EvidenceLink rows linking each bullet to its source entity.
          9. Call AICostService.log_call() with token counts.
          10. Return the list of ResumeBullet rows.

        TODO: Implement the above steps.
        """
        raise NotImplementedError(
            "Phase 1 — TODO: implement generate_bullets (see docstring for full spec)"
        )

    async def approve_bullet(
        self, user_id: uuid.UUID, resume_id: uuid.UUID, bullet_id: uuid.UUID
    ) -> ResumeBullet | None:
        """Mark a resume bullet as approved by the user."""
        bullet = await self._get_bullet_for_user(user_id, resume_id, bullet_id)
        if bullet is None:
            return None

        bullet.is_approved = True
        await self._db.flush()
        return bullet

    async def reject_bullet(self, user_id: uuid.UUID, resume_id: uuid.UUID, bullet_id: uuid.UUID) -> bool:
        """Delete a resume bullet owned by the user."""
        bullet = await self._get_bullet_for_user(user_id, resume_id, bullet_id)
        if bullet is None:
            return False

        await self._db.delete(bullet)
        await self._db.flush()
        return True

    async def snapshot_version(self, resume_id: uuid.UUID, fit_score: float | None) -> ResumeVersion:
        """Save a version snapshot of the current approved bullets.

        TODO: Create a ResumeVersion row with the current fit_score_at_gen.
        In Phase 2, also serialize the full bullet list into the version row.
        """
        raise NotImplementedError("Phase 1 — TODO: implement snapshot_version")

    async def _get_bullet_for_user(
        self, user_id: uuid.UUID, resume_id: uuid.UUID, bullet_id: uuid.UUID
    ) -> ResumeBullet | None:
        result = await self._db.execute(
            select(ResumeBullet)
            .join(Resume, Resume.id == ResumeBullet.resume_id)
            .where(
                ResumeBullet.id == bullet_id,
                ResumeBullet.resume_id == resume_id,
                Resume.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()
