"""JWT creation / validation and bcrypt password hashing."""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

ALGORITHM = "HS256"
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


# ── Password helpers ──────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ── JWT helpers ───────────────────────────────────────────────────────────────


def _create_token(data: dict[str, Any], expires_delta: timedelta, token_type: str) -> str:
    payload = data.copy()
    now = datetime.now(tz=timezone.utc)
    payload.update(
        {
            "iat": now,
            "exp": now + expires_delta,
            "type": token_type,
        }
    )
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: str) -> str:
    """Return a short-lived access JWT for the given user_id."""
    return _create_token(
        {"sub": user_id},
        timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        TOKEN_TYPE_ACCESS,
    )


def create_refresh_token(user_id: str) -> str:
    """Return a long-lived refresh JWT for the given user_id."""
    return _create_token(
        {"sub": user_id},
        timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        TOKEN_TYPE_REFRESH,
    )


def decode_access_token(token: str) -> str:
    """Decode and validate an access token. Returns the user_id (sub claim).

    Raises JWTError if the token is invalid, expired, or wrong type.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise JWTError("Token type is not 'access'")

    sub: str | None = payload.get("sub")
    if sub is None:
        raise JWTError("Token missing 'sub' claim")
    return sub


def decode_refresh_token(token: str) -> str:
    """Decode and validate a refresh token. Returns the user_id (sub claim).

    Raises JWTError if the token is invalid, expired, or wrong type.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise

    if payload.get("type") != TOKEN_TYPE_REFRESH:
        raise JWTError("Token type is not 'refresh'")

    sub: str | None = payload.get("sub")
    if sub is None:
        raise JWTError("Token missing 'sub' claim")
    return sub
