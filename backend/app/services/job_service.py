"""Job service — create, retrieve, and parse job descriptions."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload, with_loader_criteria
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import AIProvider
from app.models.job_analysis import JobAnalysis
from app.models.job_description import JobDescription
from app.schemas.job import JobDescriptionCreate


class JobService:
    def __init__(self, db: AsyncSession, ai_provider: AIProvider) -> None:
        self._db = db
        self._ai = ai_provider

    async def create(self, user_id: uuid.UUID, data: JobDescriptionCreate) -> JobDescription:
        """Persist a new job description. Does not trigger parsing immediately.

        TODO: Enqueue a Celery task to parse the JD asynchronously and update
        parsed_at once complete.
        """
        job = JobDescription(
            user_id=user_id,
            title=data.title,
            company=data.company,
            raw_text=data.raw_text,
        )
        self._db.add(job)
        await self._db.flush()
        return job

    async def list_for_user(self, user_id: uuid.UUID) -> list[JobDescription]:
        """Return all job descriptions for a user, ordered newest first."""
        result = await self._db.execute(
            select(JobDescription)
            .options(
                selectinload(JobDescription.analyses),
                with_loader_criteria(
                    JobAnalysis,
                    JobAnalysis.user_id == user_id,
                    include_aliases=True,
                ),
            )
            .where(JobDescription.user_id == user_id)
            .order_by(JobDescription.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_for_user(self, user_id: uuid.UUID, job_id: uuid.UUID) -> JobDescription | None:
        """Return a single JD, enforcing ownership."""
        result = await self._db.execute(
            select(JobDescription)
            .options(
                selectinload(JobDescription.analyses).selectinload(
                    JobAnalysis.matched_requirements
                ),
                selectinload(JobDescription.analyses).selectinload(
                    JobAnalysis.missing_requirements
                ),
                with_loader_criteria(
                    JobAnalysis,
                    JobAnalysis.user_id == user_id,
                    include_aliases=True,
                ),
            )
            .where(
                JobDescription.id == job_id,
                JobDescription.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def get_latest_analysis(job: JobDescription, user_id: uuid.UUID) -> JobAnalysis | None:
        """Return the user's most recent analysis for a job."""
        analyses = [analysis for analysis in job.analyses if analysis.user_id == user_id]
        if not analyses:
            return None
        return max(analyses, key=lambda analysis: analysis.analyzed_at)

    async def parse(self, user_id: uuid.UUID, job_id: uuid.UUID) -> JobDescription:
        """Trigger AI parsing of a job description.

        TODO:
          1. Check AICostService.check_budget() before calling AI.
          2. Call self._ai.parse_job_description(job.raw_text).
          3. Store parsed requirements as JSONB on the job or in a child table.
          4. Call AICostService.log_call() with token counts.
          5. Set job.parsed_at = now().
        """
        job = await self.get_for_user(user_id, job_id)
        if job is None:
            raise ValueError(f"JobDescription {job_id} not found for user {user_id}")

        # TODO: Implement AI parsing (see docstring above)
        job.parsed_at = datetime.now(tz=timezone.utc)
        await self._db.flush()
        return job
