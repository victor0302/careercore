"""Job parsing Celery tasks."""

import asyncio
import uuid

from botocore.exceptions import BotoCoreError
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import AsyncSessionLocal
from app.workers.celery_app import celery_app

_TRANSIENT_EXCEPTIONS = (BotoCoreError, SQLAlchemyError)


async def _parse_job_async(job_id: str, user_id: str) -> None:
    from app.ai.dependencies import get_ai_provider
    from app.services.job_service import JobService

    parsed_job_id = uuid.UUID(job_id)
    parsed_user_id = uuid.UUID(user_id)

    async with AsyncSessionLocal() as session:
        service = JobService(session, get_ai_provider())
        await service.parse(parsed_user_id, parsed_job_id)
        await session.commit()


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="ai_tasks",
    name="app.workers.tasks.job_tasks.parse_job",
)
def parse_job(self: "celery_app.Task", job_id: str, user_id: str) -> None:  # type: ignore[name-defined]
    """Parse a job description asynchronously via AI and persist requirements."""
    try:
        asyncio.run(_parse_job_async(job_id, user_id))
    except _TRANSIENT_EXCEPTIONS as exc:
        retries = getattr(self.request, "retries", 0)
        max_retries = getattr(self, "max_retries", 0)
        if retries < max_retries:
            raise self.retry(exc=exc)
    except Exception:
        pass
