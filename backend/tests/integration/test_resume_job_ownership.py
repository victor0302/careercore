"""Integration tests for POST /api/v1/resumes job_id ownership enforcement.

The shared `client` fixture can't be used here because test_engine fails on
SQLite/JSONB incompatibility.  Instead a purpose-built `resume_client` fixture
bypasses test_engine entirely: get_current_user is overridden to return a
pre-built user, and ResumeService.create is patched per-test so no real DB
tables are needed.

Scenarios:
  1. No job_id         → 201 Created
  2. Valid owned job   → 201 Created
  3. Cross-user job_id → 404 Not Found
  4. Nonexistent job   → 404 Not Found
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.services.resume_service import ResumeService


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


def _make_user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "resume-ownership-test@careercore.test"
    user.is_active = True
    return user


def _make_resume(user_id: uuid.UUID, job_id: uuid.UUID | None) -> SimpleNamespace:
    """Minimal resume-like object Pydantic's from_attributes can read."""
    return SimpleNamespace(id=uuid.uuid4(), user_id=user_id, job_id=job_id)


@pytest_asyncio.fixture
async def resume_client() -> AsyncGenerator[tuple[AsyncClient, User], None]:
    """Minimal client: auth bypassed, DB not needed for resume create endpoint."""
    user = _make_user()
    mock_db = AsyncMock(spec=AsyncSession)

    async def _db_override():
        yield mock_db

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_user] = lambda: user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, user

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# 201 paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_resume_no_job_id_returns_201(
    resume_client: tuple[AsyncClient, User],
) -> None:
    """POST /resumes with no job_id creates a resume and returns 201."""
    client, user = resume_client
    fake_resume = _make_resume(user.id, None)

    with patch.object(ResumeService, "create", AsyncMock(return_value=fake_resume)):
        resp = await client.post("/api/v1/resumes", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert body["user_id"] == str(user.id)
    assert body["job_id"] is None


@pytest.mark.asyncio
async def test_create_resume_owned_job_id_returns_201(
    resume_client: tuple[AsyncClient, User],
) -> None:
    """POST /resumes with a valid owned job_id creates a resume and returns 201."""
    client, user = resume_client
    job_id = uuid.uuid4()
    fake_resume = _make_resume(user.id, job_id)

    with patch.object(ResumeService, "create", AsyncMock(return_value=fake_resume)):
        resp = await client.post("/api/v1/resumes", json={"job_id": str(job_id)})

    assert resp.status_code == 201
    assert resp.json()["job_id"] == str(job_id)


# ---------------------------------------------------------------------------
# 404 paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_resume_cross_user_job_id_returns_404(
    resume_client: tuple[AsyncClient, User],
) -> None:
    """POST /resumes with another user's job_id returns 404 (ownership-safe)."""
    client, _ = resume_client

    with patch.object(
        ResumeService, "create", AsyncMock(side_effect=ValueError("Job not found."))
    ):
        resp = await client.post(
            "/api/v1/resumes", json={"job_id": str(uuid.uuid4())}
        )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Job not found."


@pytest.mark.asyncio
async def test_create_resume_nonexistent_job_id_returns_404(
    resume_client: tuple[AsyncClient, User],
) -> None:
    """POST /resumes with a job_id that does not exist returns 404."""
    client, _ = resume_client

    with patch.object(
        ResumeService, "create", AsyncMock(side_effect=ValueError("Job not found."))
    ):
        resp = await client.post(
            "/api/v1/resumes", json={"job_id": str(uuid.uuid4())}
        )

    assert resp.status_code == 404
