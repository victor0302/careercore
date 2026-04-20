"""Unit tests for AICostService Redis budget caching.

These tests monkeypatch the three cache helpers (_budget_cache_read,
_budget_cache_write, _budget_cache_delete) and the DB helper
(_tokens_used_today) so no real Redis or PostgreSQL connection is needed.

Scenarios:
  1. Cache hit  — check_budget() uses cached value; _tokens_used_today not called.
  2. Cache miss — check_budget() queries DB, then populates the cache.
  3. Budget exceeded via cache — BudgetExceededError raised when cached value >= budget.
  4. log_call() success — cache is invalidated.
  5. log_call() failure — cache is NOT invalidated.
  6. Parse endpoint maps BudgetExceededError to HTTP 429.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.ai_cost_service as acs_module
from app.ai.exceptions import BudgetExceededError
from app.models.ai_call_log import AICallType
from app.models.user import User, UserTier
from app.services.ai_cost_service import AICostService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(tier: UserTier = UserTier.free) -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.tier = tier
    return user


def _make_service() -> AICostService:
    db = AsyncMock()
    return AICostService(db)


# ---------------------------------------------------------------------------
# check_budget — cache hit
# ---------------------------------------------------------------------------


async def test_check_budget_cache_hit_skips_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the cache returns a value, _tokens_used_today must not be called."""
    user = _make_user()
    service = _make_service()

    async def _read_hit(redis, key: str) -> int:
        return 100  # well under the free-tier budget of 50_000

    db_called = False

    async def _no_db_query(self, user_id):
        nonlocal db_called
        db_called = True
        return 0

    monkeypatch.setattr(acs_module, "_budget_cache_read", _read_hit)
    monkeypatch.setattr(AICostService, "_tokens_used_today", _no_db_query)

    await service.check_budget(user)
    assert not db_called


# ---------------------------------------------------------------------------
# check_budget — cache miss
# ---------------------------------------------------------------------------


async def test_check_budget_cache_miss_queries_db_and_writes_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a cache miss, DB is queried and the result is written to cache."""
    user = _make_user()
    service = _make_service()

    written: dict[str, int] = {}

    async def _read_miss(redis, key: str) -> None:
        return None

    async def _db_tokens(self, user_id) -> int:
        return 1_000

    async def _write(redis, key: str, tokens: int, ttl: int) -> None:
        written[key] = tokens

    monkeypatch.setattr(acs_module, "_budget_cache_read", _read_miss)
    monkeypatch.setattr(AICostService, "_tokens_used_today", _db_tokens)
    monkeypatch.setattr(acs_module, "_budget_cache_write", _write)

    await service.check_budget(user)

    assert len(written) == 1
    assert list(written.values())[0] == 1_000


# ---------------------------------------------------------------------------
# check_budget — budget exceeded via cache
# ---------------------------------------------------------------------------


async def test_check_budget_raises_when_cached_value_at_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BudgetExceededError raised when cached token count >= budget."""
    from app.core.config import get_settings
    settings = get_settings()
    budget = settings.FREE_TIER_DAILY_TOKEN_BUDGET

    user = _make_user(UserTier.free)
    service = _make_service()

    async def _read_at_limit(redis, key: str) -> int:
        return budget  # exactly at limit

    monkeypatch.setattr(acs_module, "_budget_cache_read", _read_at_limit)

    with pytest.raises(BudgetExceededError):
        await service.check_budget(user)


# ---------------------------------------------------------------------------
# log_call — invalidates cache on success
# ---------------------------------------------------------------------------


async def test_log_call_success_deletes_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """After a successful log_call, the budget cache key must be deleted."""
    user_id = uuid.uuid4()
    service = _make_service()
    # DB flush is a no-op via AsyncMock
    service._db.flush = AsyncMock()
    service._db.add = MagicMock()

    deleted_keys: list[str] = []

    async def _delete(redis, key: str) -> None:
        deleted_keys.append(key)

    monkeypatch.setattr(acs_module, "_budget_cache_delete", _delete)

    await service.log_call(
        user_id=user_id,
        call_type=AICallType.parse_job_description,
        model="mock",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=200,
        success=True,
    )

    assert len(deleted_keys) == 1
    assert str(user_id) in deleted_keys[0]


# ---------------------------------------------------------------------------
# log_call — does NOT invalidate cache on failure
# ---------------------------------------------------------------------------


async def test_log_call_failure_does_not_delete_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed log_call must not touch the budget cache."""
    user_id = uuid.uuid4()
    service = _make_service()
    service._db.flush = AsyncMock()
    service._db.add = MagicMock()

    deleted_keys: list[str] = []

    async def _delete(redis, key: str) -> None:
        deleted_keys.append(key)

    monkeypatch.setattr(acs_module, "_budget_cache_delete", _delete)

    await service.log_call(
        user_id=user_id,
        call_type=AICallType.parse_job_description,
        model="mock",
        prompt_tokens=0,
        completion_tokens=0,
        latency_ms=50,
        success=False,
        error_message="provider error",
    )

    assert deleted_keys == []


# ---------------------------------------------------------------------------
# Parse endpoint — budget exceeded maps to 429
# ---------------------------------------------------------------------------


async def test_parse_endpoint_budget_exceeded_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    """BudgetExceededError from JobService.parse must map to HTTP 429."""
    from fastapi import HTTPException

    from app.api.v1.endpoints.jobs import parse_job
    from app.services.job_service import JobService

    user = _make_user()
    db = AsyncMock()

    async def _raise_budget(self, user_id, job_id):
        raise BudgetExceededError(str(user_id), budget=50_000, used=50_000)

    monkeypatch.setattr(JobService, "parse", _raise_budget)

    with pytest.raises(HTTPException) as exc_info:
        await parse_job(
            job_id=uuid.uuid4(),
            current_user=user,
            db=db,
            ai=None,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "Daily AI token budget exceeded."
