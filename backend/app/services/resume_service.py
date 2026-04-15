"""Resume service — generate, version, and manage resumes."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import AIProvider
from app.models.resume import Resume, ResumeBullet, ResumeVersion
from app.models.project import Project
from app.models.work_experience import WorkExperience
from app.schemas.resume import (
    EvidenceLinkRead,
    ResumeBulletWithEvidence,
    ResumeCreate,
    ResumeVersionDetailRead,
)


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

    async def get_version_detail(
        self,
        user_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> ResumeVersionDetailRead | None:
        """Return a version detail view with current approved bullets and resolved evidence."""
        result = await self._db.execute(
            select(ResumeVersion)
            .where(ResumeVersion.id == version_id)
            .options(joinedload(ResumeVersion.resume).joinedload(Resume.job))
        )
        version = result.scalar_one_or_none()
        if version is None or version.resume.user_id != user_id:
            return None

        bullets_result = await self._db.execute(
            select(ResumeBullet)
            .where(
                ResumeBullet.resume_id == version.resume_id,
                ResumeBullet.is_approved.is_(True),
            )
            .options(selectinload(ResumeBullet.evidence_links))
            .order_by(ResumeBullet.created_at)
        )
        bullets = list(bullets_result.scalars().all())

        bullet_details: list[ResumeBulletWithEvidence] = []
        for bullet in bullets:
            evidence_reads: list[EvidenceLinkRead] = []
            for link in bullet.evidence_links:
                if link.source_entity_type == "work_experience":
                    entity = await self._db.get(WorkExperience, link.source_entity_id)
                    display_name = (
                        f"{entity.role_title} at {entity.employer}" if entity else "Unknown"
                    )
                else:
                    entity = await self._db.get(Project, link.source_entity_id)
                    display_name = entity.name if entity else "Unknown"

                evidence_reads.append(
                    EvidenceLinkRead(
                        source_entity_type=link.source_entity_type,
                        source_entity_id=link.source_entity_id,
                        display_name=display_name,
                    )
                )

            bullet_details.append(
                ResumeBulletWithEvidence(
                    id=bullet.id,
                    text=bullet.text,
                    confidence=bullet.confidence,
                    evidence=evidence_reads,
                )
            )

        job = version.resume.job
        return ResumeVersionDetailRead(
            id=version.id,
            resume_id=version.resume_id,
            fit_score_at_gen=version.fit_score_at_gen,
            created_at=version.created_at,
            job_title=job.title if job else None,
            job_company=job.company if job else None,
            bullets=bullet_details,
        )

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
    ) -> ResumeBullet:
        """Mark a resume bullet as approved by the user.

        TODO: Validate ownership (resume belongs to user, bullet belongs to resume).
        Set is_approved=True and flush.
        """
        raise NotImplementedError("Phase 1 — TODO: implement approve_bullet")

    async def snapshot_version(self, resume_id: uuid.UUID, fit_score: float | None) -> ResumeVersion:
        """Save a version snapshot of the current approved bullets.

        TODO: Create a ResumeVersion row with the current fit_score_at_gen.
        In Phase 2, also serialize the full bullet list into the version row.
        """
        raise NotImplementedError("Phase 1 — TODO: implement snapshot_version")
