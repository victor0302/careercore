"""Integration tests for per-user sliding-window rate limiting on AI endpoints.

Strategy
--------
Same monkeypatch approach as test_auth_rate_limit.py.  The two low-level
sliding-window helpers in ``app.core.rate_limit`` are replaced with
in-memory fakes:

  - ``_sw_record``     — returns the next count for a given key.
  - ``_sw_oldest_ms``  — returns a fixed sentinel so Retry-After is predictable.

The ``_get_redis`` dependency is already replaced with a None sentinel by the
shared ``client`` fixture in conftest.py.

Scenarios covered:
  1. Requests within the limit are not rate-limited (status != 429).
  2. The (max_requests + 1)-th request returns 429.
  3. Rate-limited response includes a positive Retry-After header.
  4. Counter reset (window expiry) allows new requests through.
  5. Analyze and generate limits are independent per endpoint name.
  6. Two different users have independent counters.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

import pytest

import app.core.rate_limit as rl_module

_ANALYZE_LIMIT = 5   # mirrors AI_ANALYZE_RATE_LIMIT_REQUESTS default
_GENERATE_LIMIT = 10  # mirrors AI_GENERATE_RATE_LIMIT_REQUESTS default


class FakeSWStore:
    """In-memory sliding-window counter store."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._counts.clear()
        else:
            self._counts[key] = 0

    def record(self, key: str) -> int:
        self._counts[key] += 1
        return self._counts[key]


_store = FakeSWStore()


async def _fake_sw_record(redis: Any, key: str, now_ms: float, window_ms: float) -> int:
    return _store.record(key)


# Return epoch ms = 1000 (very far in the past) → Retry-After is always large and positive.
_FIXED_OLDEST_MS = 1_000.0


async def _fake_sw_oldest_ms_simple(redis: Any, key: str) -> float:
    return _FIXED_OLDEST_MS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patch_ai_rate_limit(client, monkeypatch):  # noqa: ARG001
    """Replace sliding-window helpers with in-memory fakes."""
    _store.reset()
    monkeypatch.setattr(rl_module, "_sw_record", _fake_sw_record)
    monkeypatch.setattr(rl_module, "_sw_oldest_ms", _fake_sw_oldest_ms_simple)
    yield
    _store.reset()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    """Return headers that make get_current_user resolve to a fake user."""
    return {}  # current_user is overridden via monkeypatch below


def _key(endpoint: str, user_id: uuid.UUID) -> str:
    return f"ai_rate_limit:{endpoint}:{user_id}"


# ---------------------------------------------------------------------------
# Tests — analyze (parse_job) endpoint
# ---------------------------------------------------------------------------


async def test_analyze_under_limit_not_rate_limited(
    client, patch_ai_rate_limit, mock_user, monkeypatch
) -> None:
    """Requests up to max are not rate-limited."""
    from app.core.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: mock_user

    key = _key("analyze", mock_user.id)
    for _ in range(_ANALYZE_LIMIT - 1):
        _store.record(key)

    # One more — counter reaches limit, not over it.
    response = await client.post(f"/api/v1/jobs/{uuid.uuid4()}/parse")
    assert response.status_code != 429

    del app.dependency_overrides[get_current_user]


async def test_analyze_over_limit_returns_429(
    client, patch_ai_rate_limit, mock_user, monkeypatch
) -> None:
    """The (limit+1)-th request must return 429."""
    from app.core.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: mock_user

    key = _key("analyze", mock_user.id)
    for _ in range(_ANALYZE_LIMIT):
        _store.record(key)

    response = await client.post(f"/api/v1/jobs/{uuid.uuid4()}/parse")
    assert response.status_code == 429
    assert response.json()["detail"] == "AI rate limit exceeded. Please try again later."

    del app.dependency_overrides[get_current_user]


async def test_analyze_429_includes_retry_after(
    client, patch_ai_rate_limit, mock_user
) -> None:
    """Rate-limited analyze response must include a positive Retry-After header."""
    from app.core.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: mock_user

    key = _key("analyze", mock_user.id)
    for _ in range(_ANALYZE_LIMIT):
        _store.record(key)

    response = await client.post(f"/api/v1/jobs/{uuid.uuid4()}/parse")
    assert response.status_code == 429
    assert "retry-after" in response.headers
    assert int(response.headers["retry-after"]) > 0

    del app.dependency_overrides[get_current_user]


async def test_analyze_counter_reset_allows_new_requests(
    client, patch_ai_rate_limit, mock_user
) -> None:
    """After the window resets the next request is not rate-limited."""
    from app.core.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: mock_user

    key = _key("analyze", mock_user.id)
    for _ in range(_ANALYZE_LIMIT + 1):
        _store.record(key)

    # Simulate window expiry.
    _store.reset()

    response = await client.post(f"/api/v1/jobs/{uuid.uuid4()}/parse")
    assert response.status_code != 429

    del app.dependency_overrides[get_current_user]


# ---------------------------------------------------------------------------
# Tests — generate (generate_bullets) endpoint
# ---------------------------------------------------------------------------


async def test_generate_over_limit_returns_429(
    client, patch_ai_rate_limit, mock_user
) -> None:
    """The (limit+1)-th generate request must return 429."""
    from app.core.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: mock_user

    key = _key("generate", mock_user.id)
    for _ in range(_GENERATE_LIMIT):
        _store.record(key)

    payload = {
        "profile_entity_type": "work_experience",
        "profile_entity_id": str(uuid.uuid4()),
        "requirement_ids": [str(uuid.uuid4())],
    }
    response = await client.post(f"/api/v1/resumes/{uuid.uuid4()}/bullets/generate", json=payload)
    assert response.status_code == 429
    assert "retry-after" in response.headers

    del app.dependency_overrides[get_current_user]


async def test_generate_429_includes_retry_after(
    client, patch_ai_rate_limit, mock_user
) -> None:
    """Rate-limited generate response must include a positive Retry-After header."""
    from app.core.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: mock_user

    key = _key("generate", mock_user.id)
    for _ in range(_GENERATE_LIMIT):
        _store.record(key)

    payload = {
        "profile_entity_type": "work_experience",
        "profile_entity_id": str(uuid.uuid4()),
        "requirement_ids": [str(uuid.uuid4())],
    }
    response = await client.post(f"/api/v1/resumes/{uuid.uuid4()}/bullets/generate", json=payload)
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0

    del app.dependency_overrides[get_current_user]


# ---------------------------------------------------------------------------
# Tests — endpoint independence and user independence
# ---------------------------------------------------------------------------


async def test_analyze_and_generate_limits_are_independent(
    client, patch_ai_rate_limit, mock_user
) -> None:
    """Exhausting the analyze limit must not affect the generate limit."""
    from app.core.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Max out analyze counter.
    analyze_key = _key("analyze", mock_user.id)
    for _ in range(_ANALYZE_LIMIT):
        _store.record(analyze_key)

    # Generate counter is untouched — should not be rate-limited.
    generate_key = _key("generate", mock_user.id)
    assert _store._counts[generate_key] == 0

    payload = {
        "profile_entity_type": "work_experience",
        "profile_entity_id": str(uuid.uuid4()),
        "requirement_ids": [str(uuid.uuid4())],
    }
    response = await client.post(f"/api/v1/resumes/{uuid.uuid4()}/bullets/generate", json=payload)
    assert response.status_code != 429

    del app.dependency_overrides[get_current_user]


async def test_two_users_have_independent_analyze_counters(
    client, patch_ai_rate_limit, mock_user, db
) -> None:
    """Exhausting user A's limit must not affect user B."""
    import uuid as _uuid
    from app.core.dependencies import get_current_user
    from app.core.security import hash_password
    from app.main import app
    from app.models.user import User

    user_b = User(
        id=_uuid.uuid4(),
        email="user_b@careercore.test",
        password_hash=hash_password("pass"),
        is_active=True,
    )
    db.add(user_b)
    await db.flush()

    # Max out user A.
    key_a = _key("analyze", mock_user.id)
    for _ in range(_ANALYZE_LIMIT):
        _store.record(key_a)

    # User B has a clean counter.
    key_b = _key("analyze", user_b.id)
    assert _store._counts[key_b] == 0

    app.dependency_overrides[get_current_user] = lambda: user_b
    response = await client.post(f"/api/v1/jobs/{_uuid.uuid4()}/parse")
    assert response.status_code != 429

    del app.dependency_overrides[get_current_user]
