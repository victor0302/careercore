"""Shared pytest fixtures for CareerCore backend tests.

Test DB strategy:
  - Unit tests: SQLite in-memory (fast, no services needed)
  - Integration tests: PostgreSQL (requires TEST_DATABASE_URL env var)

AI calls are always mocked -- set AI_PROVIDER=mock before running tests
or ensure it is set in the environment (it defaults to "mock" in Settings).
"""

import os

# -- Env vars MUST be set before any app module is imported -------------------
# app/db/session.py calls get_settings() at module level; if the required
# vars are missing the import itself raises a ValidationError.
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("MINIO_BUCKET", "careercore-test")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

import uuid  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.ai.providers.mock_provider import MockAIProvider  # noqa: E402
from app.core.rate_limit import _get_redis  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.profile import Profile  # noqa: E402
from app.models.user import User  # noqa: E402

_TEST_DB_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


# -- Database fixtures --------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create a test engine and all tables for the session."""
    engine = create_async_engine(_TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(test_engine) -> AsyncGenerator[AsyncSession, None]:  # type: ignore[type-arg]
    """Yield a fresh async DB session, rolled back after each test."""
    SessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
        await session.rollback()


# -- Application fixtures -----------------------------------------------------


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:  # type: ignore[type-arg]
    """Async HTTP client with DB, AI provider, and Redis overridden.

    Redis is replaced with a no-op sentinel so tests never connect to a real
    Redis instance.  Rate-limit counter logic is monkeypatched separately in
    tests/integration/api/test_auth_rate_limit.py; for all other tests the
    rate limiter is effectively disabled because _increment_counter returns 1
    (below the 10-request limit) by default when the counter store is empty.
    """
    import app.core.rate_limit as rl_module
    from collections import defaultdict

    mock_ai = MockAIProvider()

    app.dependency_overrides[get_db] = lambda: db  # type: ignore[assignment]
    # Return a sentinel None so _get_redis never creates a real aioredis client.
    app.dependency_overrides[_get_redis] = lambda: None  # type: ignore[assignment]

    from app.ai.dependencies import get_ai_provider

    app.dependency_overrides[get_ai_provider] = lambda: mock_ai  # type: ignore[assignment]

    # Replace Redis counter helpers with in-memory stubs so no real Redis call
    # is made from the RateLimiter dependency during non-rate-limit tests.
    _counts: dict[str, int] = defaultdict(int)

    async def _stub_increment(redis, key: str, window_seconds: int) -> int:
        _counts[key] += 1
        return _counts[key]

    async def _stub_ttl(redis, key: str) -> int:
        return 900

    # Sliding-window stubs for AIRateLimiter — return count=1 (below any limit)
    # so AI endpoints are effectively un-rate-limited during normal tests.
    async def _stub_sw_record(redis, key: str, now_ms: float, window_ms: float) -> int:
        _counts[key] += 1
        return _counts[key]

    async def _stub_sw_oldest_ms(redis, key: str) -> float:
        return 0.0

    original_incr = rl_module._increment_counter
    original_ttl = rl_module._get_ttl
    original_sw_record = rl_module._sw_record
    original_sw_oldest_ms = rl_module._sw_oldest_ms
    rl_module._increment_counter = _stub_increment  # type: ignore[assignment]
    rl_module._get_ttl = _stub_ttl  # type: ignore[assignment]
    rl_module._sw_record = _stub_sw_record  # type: ignore[assignment]
    rl_module._sw_oldest_ms = _stub_sw_oldest_ms  # type: ignore[assignment]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    rl_module._increment_counter = original_incr  # type: ignore[assignment]
    rl_module._get_ttl = original_ttl  # type: ignore[assignment]
    rl_module._sw_record = original_sw_record  # type: ignore[assignment]
    rl_module._sw_oldest_ms = original_sw_oldest_ms  # type: ignore[assignment]
    app.dependency_overrides.clear()


# -- Data fixtures ------------------------------------------------------------


@pytest_asyncio.fixture
async def mock_user(db: AsyncSession) -> User:
    """Create and return a test user (tier=free)."""
    from app.core.security import hash_password

    user = User(
        id=uuid.uuid4(),
        email="testuser@careercore.test",
        password_hash=hash_password("testpassword123"),
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def mock_profile(db: AsyncSession, mock_user: User) -> Profile:
    """Create and return a test profile linked to mock_user."""
    profile = Profile(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        display_name="Test User",
        current_title="Software Engineer",
        target_domain="Backend Engineering",
        completeness_pct=0.0,
    )
    db.add(profile)
    await db.flush()
    return profile


@pytest.fixture
def mock_ai_provider() -> MockAIProvider:
    """Return a MockAIProvider instance for unit tests."""
    return MockAIProvider()
