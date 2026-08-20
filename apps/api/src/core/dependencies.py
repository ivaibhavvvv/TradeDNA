import uuid
from typing import Annotated, Optional
import jwt
from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.exceptions import ForbiddenException, UnauthorizedException
from src.models.session import UserSession
from src.models.tenant import Tenant
from src.models.user import User

settings = get_settings()


def get_client_metadata(request: Request) -> tuple[str, str]:
    """Extract client IP and User-Agent from request headers."""
    ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "unknown")
    return ip, user_agent


async def get_current_user(
    request: Request,
    authorization: Annotated[Optional[str], Header()] = None,
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """
    Validate JWT Bearer Access Token or HttpOnly cookie, check session revocation,
    and return authenticated User object with eager loaded Tenant.
    """
    token: Optional[str] = None

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    elif "tradedna_access_token" in request.cookies:
        token = request.cookies.get("tradedna_access_token")

    if not token:
        raise UnauthorizedException("Missing or invalid authentication token.")

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise UnauthorizedException("Access token has expired.")
    except jwt.InvalidTokenError:
        raise UnauthorizedException("Invalid access token.")

    if payload.get("type") != "access":
        raise UnauthorizedException("Invalid token type.")

    user_id_str = payload.get("sub")
    session_id_str = payload.get("session_id")

    if not user_id_str:
        raise UnauthorizedException("Invalid token claims: missing subject.")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise UnauthorizedException("Malformed user identifier in token.")

    # Query User with eager loaded Tenant
    user_stmt = select(User).options(selectinload(User.tenant)).where(User.id == user_id)
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()

    if not user or not user.is_active:
        raise UnauthorizedException("User account is inactive or does not exist.")

    # Check Session Revocation if session_id is embedded in claims
    if session_id_str:
        try:
            session_id = uuid.UUID(session_id_str)
            session_stmt = select(UserSession).where(UserSession.id == session_id)
            session_res = await db.execute(session_stmt)
            session = session_res.scalar_one_or_none()

            if not session or session.is_revoked:
                raise UnauthorizedException("Session has been terminated or revoked.")
        except ValueError:
            raise UnauthorizedException("Malformed session identifier in token.")

    return user


async def get_current_tenant(
    current_user: Annotated[User, Depends(get_current_user)],
) -> Tenant:
    """Return the authenticated tenant belonging to the verified current user."""
    return current_user.tenant


def enforce_tenant_isolation(resource_tenant_id: uuid.UUID, current_user: User) -> None:
    """
    Authoritative boundary guard: raises 403 Forbidden if a resource does not belong
    to the authenticated user's tenant.
    """
    if current_user.tenant_id != resource_tenant_id:
        raise ForbiddenException("Cross-tenant resource access is forbidden.")
