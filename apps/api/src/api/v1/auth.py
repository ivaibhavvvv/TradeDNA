import uuid
from typing import Annotated, Optional
import jwt
from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.dependencies import (
    get_client_metadata,
    get_current_user,
)
from src.core.exceptions import UnauthorizedException
from src.core.rate_limit import rate_limit
from src.core.security import clear_auth_cookies, set_auth_cookies
from src.models.user import User
from src.schemas.auth import (
    AuthResponse,
    MessageResponse,
    SessionResponse,
    TokenRefreshRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from src.services import auth_service

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["Authentication & Tenant Management"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new User & Tenant",
    dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60, tier="AUTH"))],
)
async def register(
    request: Request,
    response: Response,
    payload: UserRegisterRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    ip, user_agent = get_client_metadata(request)
    auth_resp = await auth_service.register_user(
        db=db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        tenant_name=payload.tenant_name,
        ip_address=ip,
        user_agent=user_agent,
    )
    set_auth_cookies(response, auth_resp.access_token, auth_resp.refresh_token)
    return auth_resp


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Authenticate User and Create Session",
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, tier="AUTH"))],
)
async def login(
    request: Request,
    response: Response,
    payload: UserLoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    ip, user_agent = get_client_metadata(request)
    auth_resp = await auth_service.login_user(
        db=db,
        email=payload.email,
        password=payload.password,
        ip_address=ip,
        user_agent=user_agent,
    )
    set_auth_cookies(response, auth_resp.access_token, auth_resp.refresh_token)
    return auth_resp


@router.post(
    "/refresh",
    response_model=AuthResponse,
    summary="Rotate Refresh Token and Issue New Access Token",
    dependencies=[Depends(rate_limit(max_requests=20, window_seconds=60, tier="AUTH"))],
)
async def refresh_token(
    request: Request,
    response: Response,
    payload: Optional[TokenRefreshRequest] = None,
    db: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    ip, user_agent = get_client_metadata(request)

    raw_refresh = None
    if payload and payload.refresh_token:
        raw_refresh = payload.refresh_token
    elif "tradedna_refresh_token" in request.cookies:
        raw_refresh = request.cookies.get("tradedna_refresh_token")

    if not raw_refresh:
        raise UnauthorizedException("Missing refresh token in request body or cookie.")

    auth_resp = await auth_service.rotate_refresh_token(
        db=db,
        raw_refresh_token=raw_refresh,
        ip_address=ip,
        user_agent=user_agent,
    )
    set_auth_cookies(response, auth_resp.access_token, auth_resp.refresh_token)
    return auth_resp


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout and Revoke Current Session",
)
async def logout(
    request: Request,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    authorization: Annotated[Optional[str], Header()] = None,
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    ip, user_agent = get_client_metadata(request)
    # Extract session_id from token claims
    session_id = None
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    elif "tradedna_access_token" in request.cookies:
        token = request.cookies.get("tradedna_access_token")

    if token:
        try:
            claims = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
            if claims.get("session_id"):
                session_id = uuid.UUID(claims["session_id"])
        except Exception:
            pass

    if session_id:
        await auth_service.logout_session(
            db=db,
            session_id=session_id,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            ip_address=ip,
            user_agent=user_agent,
        )

    clear_auth_cookies(response)
    return MessageResponse(success=True, message="Successfully logged out of current session.")


@router.post(
    "/logout-all",
    response_model=MessageResponse,
    summary="Logout of All Devices & Revoke All Sessions",
)
async def logout_all(
    request: Request,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    ip, user_agent = get_client_metadata(request)
    await auth_service.logout_all_sessions(
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        ip_address=ip,
        user_agent=user_agent,
    )
    clear_auth_cookies(response)
    return MessageResponse(success=True, message="Successfully logged out of all active sessions.")


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get Authenticated User Profile",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.get(
    "/sessions",
    response_model=list[SessionResponse],
    summary="List Active User Sessions",
)
async def get_sessions(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    authorization: Annotated[Optional[str], Header()] = None,
    db: AsyncSession = Depends(get_db_session),
) -> list[SessionResponse]:
    session_id = None
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    elif "tradedna_access_token" in request.cookies:
        token = request.cookies.get("tradedna_access_token")

    if token:
        try:
            claims = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
            if claims.get("session_id"):
                session_id = uuid.UUID(claims["session_id"])
        except Exception:
            pass

    return await auth_service.list_user_sessions(
        db=db,
        user_id=current_user.id,
        current_session_id=session_id,
    )
