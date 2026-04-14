"""Unit tests for FileService.get_for_user ownership enforcement (C-3 fix)."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.uploaded_file import FileStatus, UploadedFile
from app.models.user import User
from app.services.file_service import FileService


@pytest_asyncio.fixture
async def two_users(db: AsyncSession) -> tuple[User, User]:
    """Create two distinct users in the test DB."""
    user_a = User(
        id=uuid.uuid4(),
        email="owner@careercore.test",
        password_hash=hash_password("Password123"),
        is_active=True,
    )
    user_b = User(
        id=uuid.uuid4(),
        email="attacker@careercore.test",
        password_hash=hash_password("Password123"),
        is_active=True,
    )
    db.add(user_a)
    db.add(user_b)
    await db.flush()
    return user_a, user_b


@pytest_asyncio.fixture
async def owned_file(db: AsyncSession, two_users: tuple[User, User]) -> UploadedFile:
    """Create an UploadedFile owned by user_a."""
    user_a, _ = two_users
    record = UploadedFile(
        id=uuid.uuid4(),
        user_id=user_a.id,
        original_filename="resume.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_key=f"{user_a.id}/test/resume.pdf",
        status=FileStatus.pending,
    )
    db.add(record)
    await db.flush()
    return record


async def test_get_for_user_returns_file_to_owner(
    db: AsyncSession, two_users: tuple[User, User], owned_file: UploadedFile
) -> None:
    user_a, _ = two_users
    service = FileService(db)
    result = await service.get_for_user(user_a.id, owned_file.id)
    assert result is not None
    assert result.id == owned_file.id


async def test_get_for_user_blocks_non_owner(
    db: AsyncSession, two_users: tuple[User, User], owned_file: UploadedFile
) -> None:
    _, user_b = two_users
    service = FileService(db)
    result = await service.get_for_user(user_b.id, owned_file.id)
    assert result is None


async def test_get_for_user_returns_none_for_missing_file(
    db: AsyncSession, two_users: tuple[User, User]
) -> None:
    user_a, _ = two_users
    service = FileService(db)
    result = await service.get_for_user(user_a.id, uuid.uuid4())
    assert result is None
