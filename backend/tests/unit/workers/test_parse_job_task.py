"""Unit tests for parse_job Celery task exception handling."""

from types import SimpleNamespace

import celery.exceptions
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.workers.tasks import job_tasks


def _fake_task(retries: int = 0, max_retries: int = 3) -> SimpleNamespace:
    """Build a minimal fake Celery task instance."""
    retry_exc = celery.exceptions.Retry()

    def fake_retry(exc=None):
        raise retry_exc

    return SimpleNamespace(
        request=SimpleNamespace(retries=retries),
        max_retries=max_retries,
        retry=fake_retry,
    )


def test_parse_job_logs_non_transient_exception(monkeypatch) -> None:
    monkeypatch.setattr(
        job_tasks,
        "_parse_job_async",
        lambda job_id, user_id: (_ for _ in ()).throw(ValueError("boom")),
    )

    log_calls: list[tuple] = []

    def fake_asyncio_run(coro):
        close = getattr(coro, "close", None)
        if close is not None:
            close()
        raise ValueError("boom")

    monkeypatch.setattr(job_tasks.asyncio, "run", fake_asyncio_run)
    monkeypatch.setattr(
        job_tasks.logger,
        "error",
        lambda msg, *args, **kwargs: log_calls.append((msg, args, kwargs)),
    )

    result = job_tasks.parse_job.run.__func__(_fake_task(), "fake-job-id", "fake-user-id")

    assert result is None
    assert len(log_calls) == 1
    msg, args, kwargs = log_calls[0]
    assert "fake-job-id" in args
    assert "fake-user-id" in args
    assert kwargs.get("exc_info") is True


def test_parse_job_retries_on_transient_exception(monkeypatch) -> None:
    def fake_asyncio_run(coro):
        close = getattr(coro, "close", None)
        if close is not None:
            close()
        raise SQLAlchemyError()

    monkeypatch.setattr(job_tasks.asyncio, "run", fake_asyncio_run)

    with pytest.raises(celery.exceptions.Retry):
        job_tasks.parse_job.run.__func__(_fake_task(retries=0), "jid", "uid")


def test_parse_job_does_not_retry_on_non_transient_exception(monkeypatch) -> None:
    def fake_asyncio_run(coro):
        close = getattr(coro, "close", None)
        if close is not None:
            close()
        raise ValueError("not transient")

    monkeypatch.setattr(job_tasks.asyncio, "run", fake_asyncio_run)
    monkeypatch.setattr(job_tasks.logger, "error", lambda *a, **kw: None)

    # Must return normally — no exception propagates
    result = job_tasks.parse_job.run.__func__(_fake_task(), "jid", "uid")
    assert result is None
