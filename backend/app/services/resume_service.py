"""Resume service — generate, version, and manage resumes."""

import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import AIProvider
from app.ai.schemas import BulletContext, JobRequirementItem
from app.models.ai_call_log import AICallType
from app.models.job_description import JobDescription
from app.models.job_requirement import JobRequirement
from app.models.profile import Profile
from app.models.project import Project
from app.models.resume import EvidenceLink, Resume, ResumeBullet, ResumeVersion
from app.models.user import User
from app.models.work_experience import WorkExperience
from app.schemas.resume import (
    EvidenceLinkRead,
    ResumeBulletWithEvidence,
    ResumeCreate,
    ResumeVersionDetailRead,
)
from app.services.ai_cost_service import AICostService


class ResumeService:
    def __init__(self, db: AsyncSession, ai_provider: AIProvider) -> None:
        self._db = db
        self._ai = ai_provider

    async def create(self, user_id: uuid.UUID, data: ResumeCreate) -> Resume:
        """Create a new empty resume for a user, optionally tied to a job."""
        if data.job_id is not None:
            result = await self._db.execute(
                select(JobDescription).where(
                    JobDescription.id == data.job_id,
                    JobDescription.user_id == user_id,
                )
            )
            if result.scalar_one_or_none() is None:
                raise ValueError("Job not found.")

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

    async def list_versions_for_user(
        self,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> list[tuple[ResumeVersion, str | None, str | None]]:
        """Return a user's resume versions with linked job title/company, newest first."""
        result = await self._db.execute(
            select(ResumeVersion)
            .join(Resume, ResumeVersion.resume_id == Resume.id)
            .where(Resume.user_id == user_id)
            .options(joinedload(ResumeVersion.resume).joinedload(Resume.job))
            .order_by(ResumeVersion.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        versions = list(result.scalars().unique().all())
        return [
            (
                version,
                version.resume.job.title if version.resume and version.resume.job else None,
                version.resume.job.company if version.resume and version.resume.job else None,
            )
            for version in versions
        ]

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
        user: User,
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
        """
        resume = await self.get_for_user(user.id, resume_id)
        if resume is None:
            raise ValueError("Resume not found.")

        entity_summary = await self._get_profile_entity_summary(
            user.id, profile_entity_type, profile_entity_id
        )
        requirements = await self._get_job_requirements(requirement_ids, user.id)

        cost_service = AICostService(self._db)
        await cost_service.check_budget(user)

        contexts = [
            BulletContext(
                profile_entity_type=profile_entity_type,
                profile_entity_id=profile_entity_id,
                entity_summary=entity_summary,
                target_requirement=JobRequirementItem(
                    text=requirement.requirement_text,
                    category=requirement.category.value,
                    is_required=requirement.is_required,
                ),
            )
            for requirement in requirements
        ]

        started_at = time.monotonic()
        generated_bullets, usage = await self._ai.generate_bullets(contexts)
        latency_ms = int((time.monotonic() - started_at) * 1000)

        allowed_evidence_ids = {context.profile_entity_id for context in contexts}

        saved_bullets: list[ResumeBullet] = []
        for generated in generated_bullets:
            if generated.evidence_entity_id not in allowed_evidence_ids:
                continue

            bullet = ResumeBullet(
                resume_id=resume_id,
                text=generated.text,
                is_ai_generated=True,
                is_approved=False,
                confidence=generated.confidence,
            )
            self._db.add(bullet)
            await self._db.flush()

            self._db.add(
                EvidenceLink(
                    bullet_id=bullet.id,
                    source_entity_type=generated.evidence_entity_type,
                    source_entity_id=generated.evidence_entity_id,
                )
            )
            saved_bullets.append(bullet)

        await cost_service.log_call(
            user_id=user.id,
            call_type=AICallType.generate_bullets,
            model=usage.model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            latency_ms=latency_ms,
            success=True,
        )
        await self._db.flush()
        return saved_bullets

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

    async def snapshot_version(
        self, user_id: uuid.UUID, resume_id: uuid.UUID, fit_score: float | None
    ) -> ResumeVersion | None:
        """Save a version snapshot of the current approved bullets.

        TODO: Create a ResumeVersion row with the current fit_score_at_gen.
        In Phase 2, also serialize the full bullet list into the version row.
        """
        resume = await self.get_for_user(user_id, resume_id)
        if resume is None:
            return None

        result = await self._db.execute(
            select(func.count())
            .select_from(ResumeBullet)
            .where(
                ResumeBullet.resume_id == resume_id,
                ResumeBullet.is_approved.is_(True),
            )
        )
        approved_count = result.scalar_one()
        if approved_count == 0:
            raise ValueError("No approved bullets to snapshot.")

        version = ResumeVersion(resume_id=resume_id, fit_score_at_gen=fit_score)
        self._db.add(version)
        await self._db.flush()
        return version

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

    async def _get_profile(self, user_id: uuid.UUID) -> Profile:
        result = await self._db.execute(select(Profile).where(Profile.user_id == user_id))
        profile = result.scalar_one_or_none()
        if profile is None:
            raise ValueError(f"Profile not found for user {user_id}")
        return profile

    async def _get_profile_entity_summary(
        self,
        user_id: uuid.UUID,
        profile_entity_type: str,
        profile_entity_id: uuid.UUID,
    ) -> str:
        profile = await self._get_profile(user_id)

        if profile_entity_type == "work_experience":
            result = await self._db.execute(
                select(WorkExperience).where(
                    WorkExperience.id == profile_entity_id,
                    WorkExperience.profile_id == profile.id,
                )
            )
            entity = result.scalar_one_or_none()
            if entity is None:
                raise ValueError("Work experience not found.")
            return f"{entity.role_title} at {entity.employer}"

        result = await self._db.execute(
            select(Project).where(
                Project.id == profile_entity_id,
                Project.profile_id == profile.id,
            )
        )
        entity = result.scalar_one_or_none()
        if entity is None:
            raise ValueError("Project not found.")
        return entity.name

    async def _get_job_requirements(
        self, requirement_ids: list[uuid.UUID], user_id: uuid.UUID
    ) -> list[JobRequirement]:
        if not requirement_ids:
            return []
        result = await self._db.execute(
            select(JobRequirement)
            .join(JobDescription, JobDescription.id == JobRequirement.job_id)
            .where(
                JobRequirement.id.in_(requirement_ids),
                JobDescription.user_id == user_id,
            )
        )
        return list(result.scalars().all())
