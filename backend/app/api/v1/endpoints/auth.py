"""Authentication endpoints — register, login, refresh."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.user import RefreshRequest, TokenPair, UserCreate, UserLogin, UserRead
from app.services.audit_service import AuditService
from app.services.auth_service import AuthError, AuthService

router = APIRouter()


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


@router.post("/login", response_model=TokenPair)
async def login(
    data: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Authenticate and return a JWT token pair."""
    service = AuthService(db)
    audit = AuditService(db)
    try:
        tokens = await service.login(data.email, data.password)
        await audit.log_event(
            action="user.login",
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", ""),
        )
        return tokens
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Exchange a refresh token for a new token pair."""
    service = AuthService(db)
    try:
        return await service.refresh(body.refresh_token)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
