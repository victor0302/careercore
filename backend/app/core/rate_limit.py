"""Redis-backed rate limiting dependencies.

Two strategies are provided:

Fixed-window (RateLimiter)
--------------------------
Used for auth endpoints.  INCR + EXPIRE — simple and cheap.  Window
boundaries are not user-visible so minor boundary burst is acceptable.

Sliding-window (AIRateLimiter)
-------------------------------
Used for expensive AI endpoints.  Sorted-set per user per endpoint:
ZADD current_ms, ZREMRANGEBYSCORE to evict stale entries, ZCARD for count.
Retry-After is computed from the oldest entry in the window so the client
knows exactly when its earliest slot expires.

Usage::

    from app.core.rate_limit import RateLimiter, AIRateLimiter

    _parse_limiter = AIRateLimiter("analyze", max_requests=5, window_seconds=3600)

    @router.post("/{job_id}/parse")
    async def parse_job(
        ...,
        _: None = Depends(_parse_limiter),
    ): ...
"""

from __future__ import annotations

import math
import time
from typing import Callable

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status

from app.core.config import get_settings
from app.core.dependencies import get_current_user


# ---------------------------------------------------------------------------
# Module-level Redis client pool
# ---------------------------------------------------------------------------

_redis_client: aioredis.Redis | None = None  # type: ignore[type-arg]


def _get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    """Return the module-level Redis client, creating it on first call."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


# ---------------------------------------------------------------------------
# Core counter helpers — extracted so tests can monkeypatch them
# ---------------------------------------------------------------------------


async def _increment_counter(redis: aioredis.Redis, key: str, window_seconds: int) -> int:  # type: ignore[type-arg]
    """Increment the request counter and set TTL on first use; return new count."""
    count: int = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    return count


async def _get_ttl(redis: aioredis.Redis, key: str) -> int:  # type: ignore[type-arg]
    """Return the remaining TTL (in seconds) for *key*, or 0 if not found."""
    ttl: int = await redis.ttl(key)
    return max(ttl, 0)


# ---------------------------------------------------------------------------
# Dependency factory
# ---------------------------------------------------------------------------


class RateLimiter:
    """FastAPI dependency that enforces a fixed-window rate limit by client IP.

    Parameters
    ----------
    max_requests:
        Maximum number of requests allowed within the window.
    window_seconds:
        Duration of the rate-limit window in seconds.

    The dependency raises ``HTTP 429 Too Many Requests`` when the limit is
    exceeded and includes a ``Retry-After`` header with the number of seconds
    remaining in the current window.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 900) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def __call__(
        self,
        request: Request,
        redis: aioredis.Redis = Depends(_get_redis),  # type: ignore[type-arg]
    ) -> None:
        ip = request.client.host if request.client else "unknown"
        path = request.url.path.rstrip("/")
        key = f"rate_limit:{path}:{ip}"

        count = await _increment_counter(redis, key, self.window_seconds)

        if count > self.max_requests:
            retry_after = await _get_ttl(redis, key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(math.ceil(retry_after))},
            )


def rate_limiter(max_requests: int = 10, window_seconds: int = 900) -> Callable:
    """Convenience factory that returns a ``RateLimiter`` instance.

    Prefer using ``RateLimiter`` directly when you want to pre-instantiate the
    dependency.  This helper is provided for use in ``Depends()`` one-liners::

        Depends(rate_limiter(max_requests=5, window_seconds=60))
    """
    return RateLimiter(max_requests=max_requests, window_seconds=window_seconds)


# ---------------------------------------------------------------------------
# Sliding-window helpers for AI rate limiting — extracted for monkeypatching
# ---------------------------------------------------------------------------


async def _sw_record(
    redis: aioredis.Redis,  # type: ignore[type-arg]
    key: str,
    now_ms: float,
    window_ms: float,
) -> int:
    """Add *now_ms* to the sorted set, prune entries older than the window, return count."""
    pipe = redis.pipeline()
    pipe.zadd(key, {str(now_ms): now_ms})
    pipe.zremrangebyscore(key, 0, now_ms - window_ms)
    pipe.zcard(key)
    pipe.expire(key, int(window_ms / 1000) + 1)
    results = await pipe.execute()
    return int(results[2])


async def _sw_oldest_ms(redis: aioredis.Redis, key: str) -> float:  # type: ignore[type-arg]
    """Return the score (epoch ms) of the oldest entry in the set, or 0.0 if empty."""
    entries = await redis.zrange(key, 0, 0, withscores=True)
    if not entries:
        return 0.0
    return float(entries[0][1])


# ---------------------------------------------------------------------------
# Per-user sliding-window rate limiter for AI endpoints
# ---------------------------------------------------------------------------


class AIRateLimiter:
    """FastAPI dependency that enforces a per-user sliding-window rate limit.

    Parameters
    ----------
    endpoint_name:
        Short label used in the Redis key (e.g. ``"analyze"`` or ``"generate"``).
        Limits are independent across endpoint names.
    max_requests:
        Maximum calls allowed within *window_seconds*.
    window_seconds:
        Sliding window duration in seconds.

    Raises HTTP 429 when the limit is exceeded.  The ``Retry-After`` header
    contains the number of seconds until the oldest request in the window falls
    out and a new slot opens.
    """

    def __init__(self, endpoint_name: str, max_requests: int, window_seconds: int) -> None:
        self.endpoint_name = endpoint_name
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def __call__(
        self,
        current_user=Depends(get_current_user),  # type: ignore[assignment]
        redis: aioredis.Redis = Depends(_get_redis),  # type: ignore[type-arg]
    ) -> None:
        now_ms = time.time() * 1000
        window_ms = self.window_seconds * 1000
        key = f"ai_rate_limit:{self.endpoint_name}:{current_user.id}"

        count = await _sw_record(redis, key, now_ms, window_ms)

        if count > self.max_requests:
            oldest_ms = await _sw_oldest_ms(redis, key)
            retry_after_ms = (oldest_ms + window_ms) - now_ms
            retry_after = math.ceil(max(retry_after_ms / 1000, 1))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="AI rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )
