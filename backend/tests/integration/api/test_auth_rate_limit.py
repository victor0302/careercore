"""Integration tests for Redis-backed rate limiting on auth endpoints.

Strategy
--------
fakeredis is not installed in this project's venv.  Instead, we monkeypatch
the two low-level counter helpers in ``app.core.rate_limit`` so that tests
never touch a real (or fake) Redis connection:

  - ``_increment_counter`` — driven by an in-memory dict; returns the next
    count for the given key.
  - ``_get_ttl``           — returns a fixed sentinel (e.g. 300 s) so that
    ``Retry-After`` header assertions can use a known value.

The ``_get_redis`` dependency override is already installed by the shared
``client`` fixture in ``tests/conftest.py`` (returns None sentinel).  These
tests only need to override the counter helpers with a version that drives the
count above the limit on demand.

Rate limiting fires as a FastAPI dependency before the handler body runs.
This means we can send any payload (even invalid credentials) and still
trigger 429 — we only need the counter to be above the threshold.

Tests cover:
  1. Requests 1–10 are not rate-limited (status != 429 regardless of auth).
  2. Request 11 returns 429 with Retry-After header.
  3. Counter reset: after clearing the store, subsequent requests succeed
     again (status != 429), simulating window expiry.
  4. All three rate-limited endpoints (login, register, refresh) respond
     with 429 when their counter is maxed.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pytest

import app.core.rate_limit as rl_module


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


class FakeCounterStore:
    """Simple in-memory counter store that mimics Redis INCR semantics."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._counts.clear()
        else:
            self._counts[key] = 0

    def incr(self, key: str) -> int:
        self._counts[key] += 1
        return self._counts[key]


_store = FakeCounterStore()


async def _fake_increment_counter(
    redis: Any, key: str, window_seconds: int
) -> int:
    return _store.incr(key)


async def _fake_get_ttl(redis: Any, key: str) -> int:
    return 300  # fixed sentinel — 5-minute remaining window


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patch_rate_limit(client, monkeypatch):  # noqa: ARG001
    """Replace the Redis counter helpers with in-memory fakes.

    The ``client`` argument ensures the conftest ``client`` fixture runs
    first (which installs its own stubs).  ``monkeypatch.setattr`` then
    overrides those stubs with ``_store``-backed fakes so each test can
    control and observe the counter directly.
    """
    _store.reset()
    monkeypatch.setattr(rl_module, "_increment_counter", _fake_increment_counter)
    monkeypatch.setattr(rl_module, "_get_ttl", _fake_get_ttl)
    yield
    _store.reset()


# ---------------------------------------------------------------------------
# Tests — login endpoint
# ---------------------------------------------------------------------------

# Structurally valid payloads (pass Pydantic validation) — no real credentials
# needed since rate-limit dependency fires before the handler body.
_LOGIN_PAYLOAD = {"email": "probe@example.com", "password": "ProbePass1!"}
_REGISTER_PAYLOAD = {
    "email": "probe@example.com",
    "password": "ProbePass1!",
}

_AUTH_IP = "127.0.0.1"  # IP used by httpx's ASGITransport


async def test_login_under_limit_not_rate_limited(client, patch_rate_limit, monkeypatch) -> None:
    """Requests 1–10 from the same IP must not return 429.

    We pre-seed the counter to 9 and make one request — counter reaches 10
    which is still within the limit (limit fires at > 10).  Both the auth
    service and audit service are stubbed so the request does not touch the DB.
    """
    from app.services.auth_service import AuthService, AuthError
    from app.services.audit_service import AuditService

    async def _stub_login(self, email, password):
        raise AuthError("stub")

    async def _stub_audit(self, *args, **kwargs):
        return None

    monkeypatch.setattr(AuthService, "login", _stub_login)
    monkeypatch.setattr(AuditService, "log_event", _stub_audit)

    key = f"rate_limit:/api/v1/auth/login:{_AUTH_IP}"
    for _ in range(9):
        _store.incr(key)

    response = await client.post("/api/v1/auth/login", json=_LOGIN_PAYLOAD)
    # Rate limiter did not fire (counter == 10, not > 10) — endpoint returns
    # 401 from the stubbed AuthError, not 429.
    assert response.status_code != 429


async def test_login_11th_request_returns_429(client, patch_rate_limit) -> None:
    """The 11th request (counter > 10) must return 429."""
    key = f"rate_limit:/api/v1/auth/login:{_AUTH_IP}"
    for _ in range(10):
        _store.incr(key)

    response = await client.post("/api/v1/auth/login", json=_LOGIN_PAYLOAD)
    assert response.status_code == 429
    assert response.json()["detail"] == "Too many requests. Please try again later."


async def test_login_429_includes_retry_after_header(client, patch_rate_limit) -> None:
    """A rate-limited response must include a positive Retry-After header."""
    key = f"rate_limit:/api/v1/auth/login:{_AUTH_IP}"
    for _ in range(10):
        _store.incr(key)

    response = await client.post("/api/v1/auth/login", json=_LOGIN_PAYLOAD)
    assert response.status_code == 429
    assert "retry-after" in response.headers
    retry_after = int(response.headers["retry-after"])
    assert retry_after > 0


async def test_login_counter_reset_allows_new_requests(client, patch_rate_limit, monkeypatch) -> None:
    """After the window resets (counter zeroed), requests must not be rate-limited.

    Both the auth service and audit service are stubbed so the test does not
    require a live DB session.
    """
    from app.services.auth_service import AuthService, AuthError
    from app.services.audit_service import AuditService

    async def _stub_login(self, email, password):
        raise AuthError("stub")

    async def _stub_audit(self, *args, **kwargs):
        return None

    monkeypatch.setattr(AuthService, "login", _stub_login)
    monkeypatch.setattr(AuditService, "log_event", _stub_audit)

    key = f"rate_limit:/api/v1/auth/login:{_AUTH_IP}"
    # Push counter above limit.
    for _ in range(11):
        _store.incr(key)

    # Simulate window expiry.
    _store.reset()

    # After reset, counter starts from 0 — first request (count=1) is below limit.
    response = await client.post("/api/v1/auth/login", json=_LOGIN_PAYLOAD)
    assert response.status_code != 429


# ---------------------------------------------------------------------------
# Tests — register endpoint
# ---------------------------------------------------------------------------


async def test_register_429_after_limit(client, patch_rate_limit) -> None:
    """Register endpoint must return 429 when the limit is exceeded."""
    key = f"rate_limit:/api/v1/auth/register:{_AUTH_IP}"
    for _ in range(10):
        _store.incr(key)

    # 11th attempt — rate limiter fires before Pydantic validation.
    response = await client.post("/api/v1/auth/register", json=_REGISTER_PAYLOAD)
    assert response.status_code == 429
    assert "retry-after" in response.headers


# ---------------------------------------------------------------------------
# Tests — refresh endpoint
# ---------------------------------------------------------------------------


async def test_refresh_429_after_limit(client, patch_rate_limit) -> None:
    """Refresh endpoint must return 429 when the limit is exceeded."""
    key = f"rate_limit:/api/v1/auth/refresh:{_AUTH_IP}"
    for _ in range(10):
        _store.incr(key)

    # 11th attempt — rate limiter fires before the missing-cookie check.
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 429
    assert "retry-after" in response.headers
