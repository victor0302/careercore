"""Celery application configuration."""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "careercore",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.extraction_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "ai_tasks": {"exchange": "ai_tasks", "routing_key": "ai_tasks"},
    },
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",
    task_routes={
        "app.workers.tasks.extraction_tasks.*": {"queue": "default"},
    },
    worker_prefetch_multiplier=1,  # fair dispatch for long-running AI tasks
    task_acks_late=True,
)
