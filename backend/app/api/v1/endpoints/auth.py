"""Authentication endpoints — register, login, refresh, me."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import (
    AccessTokenResponse,
    UserCreate,
    UserLogin,
    UserRead,
)
from app.services.audit_service import AuditService
from app.services.auth_service import AuthError, AuthService

router = APIRouter()
settings = get_settings()


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/api/v1/auth",
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    """Register a new user account."""
    service = AuthService(db)
    audit = AuditService(db)
    try:
        user = await service.register(data)
        await audit.log_event(
            action="user.register",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", ""),
            user_id=user.id,
            entity_type="User",
            entity_id=user.id,
        )
        return UserRead.model_validate(user)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/login", response_model=AccessTokenResponse)
async def login(
    data: UserLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AccessTokenResponse:
    """Authenticate and return an access token while setting a refresh cookie."""
    service = AuthService(db)
    audit = AuditService(db)
    try:
        user, tokens = await service.login(data.email, data.password)
        _set_refresh_cookie(response, tokens.refresh_token)
        await audit.log_event(
            action="user.login",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", ""),
            user_id=user.id,
            entity_type="User",
            entity_id=user.id,
        )
        return AccessTokenResponse(access_token=tokens.access_token)
    except AuthError as exc:
        await audit.log_event(
            action="user.login.failed",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", ""),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AccessTokenResponse:
    """Exchange a refresh token for a new access token."""
    service = AuthService(db)
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )
    try:
        tokens = await service.refresh(refresh_token)
        _set_refresh_cookie(response, tokens.refresh_token)
        return AccessTokenResponse(access_token=tokens.access_token)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Invalidate all active refresh tokens and clear the refresh cookie."""
    service = AuthService(db)
    audit = AuditService(db)
    await service.logout(current_user.id)
    response.delete_cookie(key="refresh_token", path="/api/v1/auth")
    await audit.log_event(
        action="user.logout",
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
        user_id=current_user.id,
        entity_type="User",
        entity_id=current_user.id,
    )


@router.get("/me", response_model=UserRead)
async def me(
    current_user: User = Depends(get_current_user),
) -> UserRead:
    """Return the currently authenticated user."""
    return UserRead.model_validate(current_user)
