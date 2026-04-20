"""Integration tests for GET /health endpoint.

Mocks aioredis.from_url (module-level import in health.py) and boto3.client
(inline import inside try-block, so patched at source) to avoid real services.
Uses a minimal DB mock instead of test_engine to bypass the SQLite/JSONB issue
that affects other integration tests — SELECT 1 needs no model tables at all.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.main import app

settings = get_settings()


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def health_client() -> AsyncGenerator[AsyncClient, None]:
    """Minimal client for health tests — no engine or real Redis/MinIO needed."""
    mock_db = AsyncMock(spec=AsyncSession)

    async def _db_override():
        yield mock_db

    app.dependency_overrides[get_db] = _db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok_redis() -> AsyncMock:
    r = AsyncMock()
    r.ping = AsyncMock()
    r.aclose = AsyncMock()
    return r


def _ok_s3() -> MagicMock:
    s3 = MagicMock()
    s3.head_bucket = MagicMock()
    return s3


# ---------------------------------------------------------------------------
# 200 paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_200_all_ok(health_client: AsyncClient) -> None:
    """All three dependency checks pass → 200 and status 'ok'."""
    with (
        patch("app.api.v1.endpoints.health.aioredis.from_url", return_value=_ok_redis()),
        patch("boto3.client", return_value=_ok_s3()),
    ):
        resp = await health_client.get("/api/v1/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "connected"
    assert body["redis"] == "connected"
    assert body["storage"] == "connected"


@pytest.mark.asyncio
async def test_health_version_from_config(health_client: AsyncClient) -> None:
    """Response 'version' field matches settings.APP_VERSION."""
    with (
        patch("app.api.v1.endpoints.health.aioredis.from_url", return_value=_ok_redis()),
        patch("boto3.client", return_value=_ok_s3()),
    ):
        resp = await health_client.get("/api/v1/health")

    assert resp.status_code == 200
    assert resp.json()["version"] == settings.APP_VERSION


@pytest.mark.asyncio
async def test_health_no_auth_required(health_client: AsyncClient) -> None:
    """No Authorization header must not produce 401 or 403."""
    with (
        patch("app.api.v1.endpoints.health.aioredis.from_url", return_value=_ok_redis()),
        patch("boto3.client", return_value=_ok_s3()),
    ):
        resp = await health_client.get("/api/v1/health")

    assert resp.status_code not in (401, 403)


# ---------------------------------------------------------------------------
# 503 paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_503_on_redis_failure(health_client: AsyncClient) -> None:
    """Redis ping raises → 503 with redis='error', others still 'connected'."""
    failing_redis = AsyncMock()
    failing_redis.ping = AsyncMock(side_effect=Exception("Redis down"))
    failing_redis.aclose = AsyncMock()

    with (
        patch("app.api.v1.endpoints.health.aioredis.from_url", return_value=failing_redis),
        patch("boto3.client", return_value=_ok_s3()),
    ):
        resp = await health_client.get("/api/v1/health")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["redis"] == "error"
    assert body["db"] == "connected"
    assert body["storage"] == "connected"


@pytest.mark.asyncio
async def test_health_503_on_storage_failure(health_client: AsyncClient) -> None:
    """head_bucket raises → 503 with storage='error', others still 'connected'."""
    failing_s3 = MagicMock()
    failing_s3.head_bucket = MagicMock(side_effect=Exception("MinIO down"))

    with (
        patch("app.api.v1.endpoints.health.aioredis.from_url", return_value=_ok_redis()),
        patch("boto3.client", return_value=failing_s3),
    ):
        resp = await health_client.get("/api/v1/health")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["storage"] == "error"
    assert body["db"] == "connected"
    assert body["redis"] == "connected"


@pytest.mark.asyncio
async def test_health_503_on_db_failure(health_client: AsyncClient) -> None:
    """DB execute raises → 503 with db='error', others still 'connected'."""
    failing_db = AsyncMock(spec=AsyncSession)
    failing_db.execute = AsyncMock(side_effect=Exception("DB down"))

    async def _failing_db_override():
        yield failing_db

    app.dependency_overrides[get_db] = _failing_db_override

    with (
        patch("app.api.v1.endpoints.health.aioredis.from_url", return_value=_ok_redis()),
        patch("boto3.client", return_value=_ok_s3()),
    ):
        resp = await health_client.get("/api/v1/health")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["db"] == "error"
    assert body["redis"] == "connected"
    assert body["storage"] == "connected"
