"""Authentication service — registration, login, token refresh."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.models.profile import Profile
from app.models.user import User
from app.schemas.user import TokenPair, UserCreate


class AuthError(Exception):
    """Raised for authentication failures (wrong credentials, duplicate email, etc.)."""


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

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
            refresh_token=create_refresh_token(str(user.id)),
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        """Validate a refresh token and issue a new token pair.

        Raises AuthError if the refresh token is invalid or the user no longer exists.

        TODO: Implement refresh token rotation — store issued refresh tokens in Redis
        and invalidate the old one when a new pair is issued. This prevents token reuse
        after logout or token theft.
        """
        from jose import JWTError

        try:
            user_id = decode_refresh_token(refresh_token)
        except JWTError as exc:
            raise AuthError("Invalid or expired refresh token.") from exc

        import uuid

        user = await self._db.get(User, uuid.UUID(user_id))
        if user is None or not user.is_active:
            raise AuthError("User not found or account disabled.")

        return TokenPair(
            access_token=create_access_token(str(user.id)),
            refresh_token=create_refresh_token(str(user.id)),
        )
