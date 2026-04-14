"""Authentication service — registration, login, token refresh."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_refresh_token,
    hash_password,
    verify_password,
)
from app.models.profile import Profile
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.user import TokenPair, UserCreate

settings = get_settings()


class AuthError(Exception):
    """Raised for authentication failures (wrong credentials, duplicate email, etc.)."""


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _issue_refresh_token(self, user_id: uuid.UUID) -> str:
        refresh_token = create_refresh_token(str(user_id))
        self._db.add(
            RefreshToken(
                user_id=user_id,
                token_hash=hash_refresh_token(refresh_token),
                expires_at=datetime.now(tz=timezone.utc)
                + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
            )
        )
        await self._db.flush()
        return refresh_token

    async def register(self, data: UserCreate) -> User:
        """Create a new user. Raises AuthError if the email is already taken."""
        existing = await self._db.execute(select(User).where(User.email == data.email))
        if existing.scalar_one_or_none() is not None:
            raise AuthError("A user with this email already exists.")

        user = User(
            email=data.email,
            password_hash=hash_password(data.password),
        )
        self._db.add(user)
        await self._db.flush()

        profile = Profile(user_id=user.id)
        self._db.add(profile)
        await self._db.flush()

        return user

    async def login(self, email: str, password: str) -> tuple[User, TokenPair]:
        """Verify credentials and return an access + refresh token pair.

        Raises AuthError if credentials are invalid or user is inactive.
        """
        result = await self._db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("Invalid email or password.")
        if not user.is_active:
            raise AuthError("Account is disabled. Contact support.")

        return user, TokenPair(
            access_token=create_access_token(str(user.id)),
            refresh_token=await self._issue_refresh_token(user.id),
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        """Validate a refresh token and issue a rotated token pair."""
        from jose import JWTError

        try:
            user_id = decode_refresh_token(refresh_token)
        except JWTError as exc:
            raise AuthError("Invalid or expired refresh token.") from exc

        token_result = await self._db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(refresh_token)
            )
        )
        stored_token = token_result.scalar_one_or_none()
        if stored_token is None:
            raise AuthError("Invalid or expired refresh token.")
        if stored_token.used_at is not None:
            raise AuthError("Invalid or expired refresh token.")
        if stored_token.expires_at <= datetime.now(tz=timezone.utc):
            raise AuthError("Invalid or expired refresh token.")

        user = await self._db.get(User, uuid.UUID(user_id))
        if user is None or not user.is_active:
            raise AuthError("User not found or account disabled.")

        stored_token.used_at = datetime.now(tz=timezone.utc)
        new_refresh_token = await self._issue_refresh_token(user.id)

        return TokenPair(
            access_token=create_access_token(str(user.id)),
            refresh_token=new_refresh_token,
        )

    async def logout(self, user_id: uuid.UUID) -> None:
        """Invalidate all active refresh tokens for *user_id*.

        Sets ``used_at`` to now on every token that is still valid (not yet
        used and not expired).  This prevents any existing refresh token from
        being exchanged after logout, regardless of which device it came from.
        """
        now = datetime.now(tz=timezone.utc)
        result = await self._db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.used_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )
        for token in result.scalars().all():
            token.used_at = now
        await self._db.flush()
