"""Shared pytest fixtures for CareerCore backend tests.

Test DB strategy:
  - Unit tests: SQLite in-memory (fast, no services needed)
  - Integration tests: PostgreSQL (requires TEST_DATABASE_URL env var)

AI calls are always mocked — set AI_PROVIDER=mock before running tests
or ensure it is set in the environment (it defaults to "mock" in Settings).
"""

import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.providers.mock_provider import MockAIProvider
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.profile import Profile
from app.models.user import User

# ── Ensure AI_PROVIDER is mock for all tests ──────────────────────────────────
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

_TEST_DB_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


# ── Database fixtures ─────────────────────────────────────────────────────────


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


# ── Application fixtures ──────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:  # type: ignore[type-arg]
    """Async HTTP client with DB and AI provider overridden."""
    mock_ai = MockAIProvider()

    app.dependency_overrides[get_db] = lambda: db  # type: ignore[assignment]

    from app.ai.dependencies import get_ai_provider

    app.dependency_overrides[get_ai_provider] = lambda: mock_ai  # type: ignore[assignment]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


# ── Data fixtures ─────────────────────────────────────────────────────────────


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
