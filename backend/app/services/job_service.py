"""Job service — create, retrieve, and parse job descriptions."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.provider import AIProvider
from app.models.ai_call_log import AICallType
from app.models.job_description import JobDescription
from app.models.job_requirement import JobRequirement
from app.models.user import User
from app.schemas.job import JobDescriptionCreate
from app.services.ai_cost_service import AICostService


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
            .where(JobDescription.user_id == user_id)
            .order_by(JobDescription.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_for_user(self, user_id: uuid.UUID, job_id: uuid.UUID) -> JobDescription | None:
        """Return a single JD, enforcing ownership."""
        result = await self._db.execute(
            select(JobDescription).where(
                JobDescription.id == job_id,
                JobDescription.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def parse(self, user_id: uuid.UUID, job_id: uuid.UUID) -> JobDescription:
        """Trigger AI parsing of a job description and persist requirements."""
        result = await self._db.execute(
            select(JobDescription)
            .options(selectinload(JobDescription.requirements))
            .where(
                JobDescription.id == job_id,
                JobDescription.user_id == user_id,
            )
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError(f"JobDescription {job_id} not found for user {user_id}")

        user = await self._db.get(User, user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found")

        cost_service = AICostService(self._db)
        await cost_service.check_budget(user)

        try:
            parsed, usage = await self._ai.parse_job_description(job.raw_text)
        except Exception as exc:
            await cost_service.log_call(
                user_id=user_id,
                call_type=AICallType.parse_job_description,
                model=getattr(self._ai, "parse_job_model", "unknown"),
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=0,
                success=False,
                error_message=str(exc),
            )
            raise

        job.requirements.clear()
        for requirement in parsed.requirements:
            job.requirements.append(
                JobRequirement(
                    id=requirement.id,
                    text=requirement.text,
                    category=requirement.category,
                    is_required=requirement.is_required,
                )
            )

        job.parsed_at = datetime.now(tz=timezone.utc)
        await cost_service.log_call(
            user_id=user_id,
            call_type=AICallType.parse_job_description,
            model=usage.model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            latency_ms=usage.latency_ms,
            success=True,
        )
        await self._db.flush()
        return job
