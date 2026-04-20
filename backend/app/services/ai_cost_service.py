"""AI cost service — token budget enforcement and call logging.

Every AI call must go through this service:
  1. Call check_budget() before invoking the provider.
  2. Call log_call() after the call completes (success or failure).

Budget limits are read from config (FREE_TIER_DAILY_TOKEN_BUDGET,
STANDARD_DAILY_TOKEN_BUDGET) and checked against the sum of total_tokens
in ai_call_logs for the current UTC day.

Redis caching
-------------
check_budget() caches the daily token total in Redis under
``budget:{user_id}:{YYYY-MM-DD}`` with a TTL set to expire at midnight UTC.
On a cache miss the DB is queried and the result is stored.  log_call()
deletes the key after a successful write so the next check reads a fresh
count.  All Redis operations are best-effort; a Redis outage falls back to
the DB transparently.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.exceptions import BudgetExceededError
from app.core.config import get_settings
from app.models.ai_call_log import AICallLog, AICallType
from app.models.user import User, UserTier

settings = get_settings()


def _cost_usd(model: str, total_tokens: int) -> float:
    rate = settings.ai_model_pricing.get(model, settings.ai_model_pricing["default"])
    return (total_tokens / 1_000_000) * rate


def _budget_key(user_id: uuid.UUID, date_str: str) -> str:
    return f"budget:{user_id}:{date_str}"


def _ttl_until_midnight_utc() -> int:
    """Seconds from now until the next UTC midnight (minimum 1)."""
    now = datetime.now(tz=timezone.utc)
    tomorrow = now.date() + timedelta(days=1)
    midnight = datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=timezone.utc)
    return max(int((midnight - now).total_seconds()) + 1, 1)


def _get_redis():
    """Return the shared Redis client (from the rate-limit pool), or None."""
    try:
        from app.core.rate_limit import _get_redis as _rl_get
        return _rl_get()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Redis cache helpers — module-level so tests can monkeypatch them
# ---------------------------------------------------------------------------


async def _budget_cache_read(redis, key: str) -> int | None:
    """Return cached token count, or None on miss or Redis unavailability."""
    if redis is None:
        return None
    try:
        val = await redis.get(key)
        return int(val) if val is not None else None
    except Exception:
        return None


async def _budget_cache_write(redis, key: str, tokens: int, ttl: int) -> None:
    """Store token count with TTL. Best-effort — never raises."""
    if redis is None:
        return
    try:
        await redis.set(key, tokens, ex=ttl)
    except Exception:
        pass


async def _budget_cache_delete(redis, key: str) -> None:
    """Delete the cache entry. Best-effort — never raises."""
    if redis is None:
        return
    try:
        await redis.delete(key)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AICostService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _tokens_used_today(self, user_id: uuid.UUID) -> int:
        """Sum total_tokens for this user in the current UTC calendar day."""
        today = datetime.now(tz=timezone.utc).date()
        result = await self._db.execute(
            select(func.coalesce(func.sum(AICallLog.total_tokens), 0)).where(
                AICallLog.user_id == user_id,
                func.date(AICallLog.created_at) == today,
                AICallLog.success.is_(True),
            )
        )
        return int(result.scalar_one())

    async def check_budget(self, user: User) -> None:
        """Raise BudgetExceededError if the user has exhausted their daily token budget.

        Reads from Redis cache first; falls back to DB on miss or Redis error.
        Cache TTL is set to expire at midnight UTC.
        """
        budget = (
            settings.STANDARD_DAILY_TOKEN_BUDGET
            if user.tier == UserTier.standard
            else settings.FREE_TIER_DAILY_TOKEN_BUDGET
        )

        today = datetime.now(tz=timezone.utc).date().isoformat()
        key = _budget_key(user.id, today)
        redis = _get_redis()

        used = await _budget_cache_read(redis, key)
        if used is None:
            used = await self._tokens_used_today(user.id)
            ttl = _ttl_until_midnight_utc()
            await _budget_cache_write(redis, key, used, ttl)

        if used >= budget:
            raise BudgetExceededError(str(user.id), budget, used)

    async def log_call(
        self,
        user_id: uuid.UUID,
        call_type: AICallType,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        success: bool,
        error_message: str | None = None,
    ) -> None:
        """Write an immutable AICallLog row.

        On success, invalidates the Redis budget cache so the next
        check_budget() call reads a fresh total from the DB.
        """
        total = prompt_tokens + completion_tokens
        entry = AICallLog(
            user_id=user_id,
            call_type=call_type,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost_usd=_cost_usd(model, total),
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
            created_at=datetime.now(tz=timezone.utc),
        )
        self._db.add(entry)
        await self._db.flush()

        if success:
            today = datetime.now(tz=timezone.utc).date().isoformat()
            key = _budget_key(user_id, today)
            redis = _get_redis()
            await _budget_cache_delete(redis, key)
