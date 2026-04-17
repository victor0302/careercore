"""Redis-backed fixed-window rate limiting dependency.

Strategy: INCR + EXPIRE (fixed window)
--------------------------------------
On each request, the counter for the current window key is incremented with
INCR.  The first INCR for a key (counter == 1) also sets an EXPIRE so the key
expires automatically after ``window_seconds``.  If the counter exceeds
``max_requests`` a 429 is raised with a ``Retry-After`` header whose value is
the remaining TTL of the window key.

This is simpler and cheaper than a sorted-set sliding window and is correct for
the auth use-case where the window boundaries are not user-visible.

Usage::

    from app.core.rate_limit import RateLimiter

    @router.post("/login")
    async def login(
        ...,
        _: None = Depends(RateLimiter(max_requests=10, window_seconds=900)),
    ): ...
"""

from __future__ import annotations

import math
from typing import Callable

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status

from app.core.config import get_settings


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
