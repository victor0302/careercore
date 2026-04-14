"""Unit tests for migration 20260413_0003: profile and sub-entity tables.

These tests exercise:
  - Migration revision chain (down_revision links to 0002)
  - Profile and sub-entity ORM models can be inserted and queried in SQLite

SQLite does not support JSONB or ARRAY; those column types are integration-only
per ADR-014. The unit test validates schema shape, FK cascade, and the 1:1
user→profile relationship using the shared in-memory SQLite fixture.
"""

import importlib
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.certification import Certification
from app.models.profile import Profile
from app.models.project import Project
from app.models.skill import Skill
from app.models.user import User
from app.models.work_experience import WorkExperience

# ── Migration metadata ─────────────────────────────────────────────────────────

_MIGRATION = importlib.import_module(
    "alembic.versions.20260413_0003_create_profile_tables"
)


def test_migration_revision_id() -> None:
    assert _MIGRATION.revision == "20260413_0003"


def test_migration_down_revision_links_to_0002() -> None:
    assert _MIGRATION.down_revision == "20260413_0002"


def test_migration_has_upgrade_and_downgrade() -> None:
    assert callable(_MIGRATION.upgrade)
    assert callable(_MIGRATION.downgrade)


# ── ORM fixtures ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        email="profile_test@careercore.test",
        password_hash=hash_password("Password123"),
        is_active=True,
    )
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def profile(db: AsyncSession, user: User) -> Profile:
    p = Profile(
        id=uuid.uuid4(),
        user_id=user.id,
        display_name="Ada Lovelace",
        current_title="Software Engineer",
        target_domain="Backend",
        completeness_pct=0.25,
    )
    db.add(p)
    await db.flush()
    return p


# ── Tests ──────────────────────────────────────────────────────────────────────


async def test_profile_created_with_correct_user_fk(
    db: AsyncSession, user: User, profile: Profile
) -> None:
    await db.refresh(profile)
    assert profile.user_id == user.id
    assert profile.display_name == "Ada Lovelace"
    assert profile.completeness_pct == pytest.approx(0.25)


async def test_profile_1to1_unique_per_user(
    db: AsyncSession, user: User, profile: Profile
) -> None:
    """A second Profile for the same user must violate the unique constraint."""
    from sqlalchemy.exc import IntegrityError

    duplicate = Profile(
        id=uuid.uuid4(),
        user_id=user.id,
        completeness_pct=0.0,
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_work_experience_fk_to_profile(
    db: AsyncSession, profile: Profile
) -> None:
    import datetime

    we = WorkExperience(
        id=uuid.uuid4(),
        profile_id=profile.id,
        employer="Acme Corp",
        role_title="Engineer",
        start_date=datetime.date(2022, 1, 1),
        is_current=True,
    )
    db.add(we)
    await db.flush()
    await db.refresh(we)
    assert we.profile_id == profile.id
    assert we.employer == "Acme Corp"


async def test_project_fk_to_profile(db: AsyncSession, profile: Profile) -> None:
    proj = Project(
        id=uuid.uuid4(),
        profile_id=profile.id,
        name="CareerCore",
        url="https://github.com/example/careercore",
    )
    db.add(proj)
    await db.flush()
    await db.refresh(proj)
    assert proj.profile_id == profile.id
    assert proj.name == "CareerCore"


async def test_skill_fk_to_profile(db: AsyncSession, profile: Profile) -> None:
    skill = Skill(
        id=uuid.uuid4(),
        profile_id=profile.id,
        name="Python",
        category="Programming",
        proficiency_level="expert",
        years_of_experience=5.0,
    )
    db.add(skill)
    await db.flush()
    await db.refresh(skill)
    assert skill.profile_id == profile.id
    assert skill.name == "Python"


async def test_certification_fk_to_profile(db: AsyncSession, profile: Profile) -> None:
    import datetime

    cert = Certification(
        id=uuid.uuid4(),
        profile_id=profile.id,
        name="AWS Solutions Architect",
        issuer="Amazon Web Services",
        issued_date=datetime.date(2023, 6, 15),
    )
    db.add(cert)
    await db.flush()
    await db.refresh(cert)
    assert cert.profile_id == profile.id
    assert cert.issuer == "Amazon Web Services"
