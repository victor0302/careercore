"""Unit tests for ResumeService.create() job_id ownership validation.

These tests mock db.execute so no real database is needed.  All four cases
the acceptance criteria require are covered at the service layer here; the
HTTP-layer mapping (ValueError → 404) is verified in
tests/integration/test_resume_job_ownership.py.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.job_description import JobDescription
from app.schemas.resume import ResumeCreate
from app.services.resume_service import ResumeService


def _make_service() -> ResumeService:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return ResumeService(db, MagicMock())


def _execute_returning(row) -> AsyncMock:
    """Return an AsyncMock for db.execute whose result yields `row`."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    return AsyncMock(return_value=mock_result)


# ---------------------------------------------------------------------------
# No job_id — ownership check skipped entirely
# ---------------------------------------------------------------------------


async def test_create_without_job_id_skips_ownership_check() -> None:
    """When job_id is None, db.execute must not be called and create succeeds."""
    service = _make_service()
    service._db.execute = AsyncMock()

    await service.create(user_id=uuid.uuid4(), data=ResumeCreate(job_id=None))

    service._db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Owned job_id — check passes and resume is created
# ---------------------------------------------------------------------------


async def test_create_with_owned_job_id_succeeds() -> None:
    """When the queried job belongs to the user, create returns a Resume."""
    service = _make_service()
    owned_job = MagicMock(spec=JobDescription)
    service._db.execute = _execute_returning(owned_job)

    resume = await service.create(user_id=uuid.uuid4(), data=ResumeCreate(job_id=uuid.uuid4()))

    assert resume is not None
    service._db.add.assert_called_once()
    service._db.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# Cross-user job_id — ownership check returns None → ValueError
# ---------------------------------------------------------------------------


async def test_create_with_cross_user_job_id_raises() -> None:
    """When the job exists but belongs to a different user, ValueError is raised."""
    service = _make_service()
    service._db.execute = _execute_returning(None)  # row not found for this user

    with pytest.raises(ValueError, match="Job not found"):
        await service.create(user_id=uuid.uuid4(), data=ResumeCreate(job_id=uuid.uuid4()))

    service._db.add.assert_not_called()


# ---------------------------------------------------------------------------
# Nonexistent job_id — ownership check returns None → same ValueError
# ---------------------------------------------------------------------------


async def test_create_with_nonexistent_job_id_raises() -> None:
    """When no job row exists at all for the given UUID, ValueError is raised."""
    service = _make_service()
    service._db.execute = _execute_returning(None)

    with pytest.raises(ValueError, match="Job not found"):
        await service.create(user_id=uuid.uuid4(), data=ResumeCreate(job_id=uuid.uuid4()))
