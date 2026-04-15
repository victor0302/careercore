"""Resume service — generate, version, and manage resumes."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.provider import AIProvider
from app.ai.schemas import BulletContext, JobRequirementItem
from app.models.ai_call_log import AICallType
from app.models.job_analysis import JobAnalysis
from app.models.job_requirement import JobRequirement
from app.models.profile import Profile
from app.models.project import Project
from app.models.resume import EvidenceLink, Resume, ResumeBullet, ResumeVersion
from app.models.user import User
from app.models.work_experience import WorkExperience
from app.schemas.resume import ResumeCreate
from app.services.ai_cost_service import AICostService


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
        user: User,
        resume_id: uuid.UUID,
    ) -> list[ResumeBullet]:
        """Generate evidence-backed resume bullets from the resume's latest job analysis."""
        resume = await self.get_for_user(user.id, resume_id)
        if resume is None:
            raise ValueError("Resume not found.")
        if resume.job_id is None:
            raise ValueError("Resume is not linked to a job description.")

        analysis = await self._get_latest_analysis(user.id, resume.job_id)
        if analysis is None:
            raise ValueError("No job analysis available for resume.")

        contexts = await self._build_bullet_contexts(user.id, analysis, resume.job_id)
        if not contexts:
            return []

        cost_service = AICostService(self._db)
        await cost_service.check_budget(user)

        try:
            generated_bullets, usage = await self._ai.generate_bullets(contexts)
        except Exception as exc:
            await cost_service.log_call(
                user_id=user.id,
                call_type=AICallType.generate_bullets,
                model=getattr(self._ai, "generate_bullets_model", "unknown"),
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=0,
                success=False,
                error_message=str(exc),
            )
            raise

        allowed_evidence = {
            (context.profile_entity_type, context.profile_entity_id) for context in contexts
        }

        saved_bullets: list[ResumeBullet] = []
        for generated in generated_bullets:
            evidence_key = (generated.evidence_entity_type, generated.evidence_entity_id)
            if evidence_key not in allowed_evidence:
                continue

            bullet = ResumeBullet(
                resume_id=resume.id,
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
            latency_ms=usage.latency_ms,
            success=True,
        )
        await self._db.flush()
        return saved_bullets

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

    async def _get_latest_analysis(
        self, user_id: uuid.UUID, job_id: uuid.UUID
    ) -> JobAnalysis | None:
        result = await self._db.execute(
            select(JobAnalysis)
            .options(selectinload(JobAnalysis.matched_requirements))
            .where(
                JobAnalysis.job_id == job_id,
                JobAnalysis.user_id == user_id,
            )
            .order_by(JobAnalysis.analyzed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _build_bullet_contexts(
        self,
        user_id: uuid.UUID,
        analysis: JobAnalysis,
        job_id: uuid.UUID,
    ) -> list[BulletContext]:
        if not analysis.matched_requirements:
            return []

        profile = await self._get_profile(user_id)
        requirement_ids = {match.requirement_id for match in analysis.matched_requirements}
        requirements = await self._get_requirements(job_id, requirement_ids)

        work_experience_ids = {
            match.source_entity_id
            for match in analysis.matched_requirements
            if match.source_entity_type == "work_experience"
        }
        project_ids = {
            match.source_entity_id
            for match in analysis.matched_requirements
            if match.source_entity_type == "project"
        }

        work_experiences = await self._get_work_experiences(profile.id, work_experience_ids)
        projects = await self._get_projects(profile.id, project_ids)

        contexts: list[BulletContext] = []
        for match in analysis.matched_requirements:
            requirement = requirements.get(match.requirement_id)
            if requirement is None:
                continue

            if match.source_entity_type == "work_experience":
                entity = work_experiences.get(match.source_entity_id)
                if entity is None:
                    continue
                entity_summary = self._summarize_work_experience(entity)
            elif match.source_entity_type == "project":
                entity = projects.get(match.source_entity_id)
                if entity is None:
                    continue
                entity_summary = self._summarize_project(entity)
            else:
                continue

            contexts.append(
                BulletContext(
                    profile_entity_type=match.source_entity_type,
                    profile_entity_id=match.source_entity_id,
                    entity_summary=entity_summary,
                    target_requirement=JobRequirementItem(
                        id=requirement.id,
                        text=requirement.requirement_text,
                        category=requirement.category.value,
                        is_required=requirement.is_required,
                    ),
                )
            )

        return contexts

    async def _get_profile(self, user_id: uuid.UUID) -> Profile:
        result = await self._db.execute(select(Profile).where(Profile.user_id == user_id))
        profile = result.scalar_one_or_none()
        if profile is None:
            raise ValueError(f"Profile not found for user {user_id}")
        return profile

    async def _get_requirements(
        self, job_id: uuid.UUID, requirement_ids: set[uuid.UUID]
    ) -> dict[uuid.UUID, JobRequirement]:
        if not requirement_ids:
            return {}
        result = await self._db.execute(
            select(JobRequirement).where(
                JobRequirement.job_id == job_id,
                JobRequirement.id.in_(requirement_ids),
            )
        )
        return {requirement.id: requirement for requirement in result.scalars().all()}

    async def _get_work_experiences(
        self, profile_id: uuid.UUID, entity_ids: set[uuid.UUID]
    ) -> dict[uuid.UUID, WorkExperience]:
        if not entity_ids:
            return {}
        result = await self._db.execute(
            select(WorkExperience).where(
                WorkExperience.profile_id == profile_id,
                WorkExperience.id.in_(entity_ids),
            )
        )
        return {entity.id: entity for entity in result.scalars().all()}

    async def _get_projects(
        self, profile_id: uuid.UUID, entity_ids: set[uuid.UUID]
    ) -> dict[uuid.UUID, Project]:
        if not entity_ids:
            return {}
        result = await self._db.execute(
            select(Project).where(
                Project.profile_id == profile_id,
                Project.id.in_(entity_ids),
            )
        )
        return {entity.id: entity for entity in result.scalars().all()}

    @staticmethod
    def _summarize_work_experience(entity: WorkExperience) -> str:
        parts = [
            f"{entity.role_title} at {entity.employer}",
            entity.description_raw,
            ResumeService._join_list(entity.bullets),
            ResumeService._join_list(entity.skill_tags),
            ResumeService._join_list(entity.tool_tags),
            ResumeService._join_list(entity.domain_tags),
        ]
        return ". ".join(part for part in parts if part)

    @staticmethod
    def _summarize_project(entity: Project) -> str:
        parts = [
            entity.name,
            entity.description_raw,
            ResumeService._join_list(entity.bullets),
            ResumeService._join_list(entity.skill_tags),
            ResumeService._join_list(entity.tool_tags),
            ResumeService._join_list(entity.domain_tags),
        ]
        return ". ".join(part for part in parts if part)

    @staticmethod
    def _join_list(values: list[str] | None) -> str | None:
        if not values:
            return None
        return ", ".join(values)
