import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import get_settings
from src.core.exceptions import UnauthorizedException, ValidationException
from src.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from src.models.session import RefreshToken, UserSession
from src.models.tenant import Tenant
from src.models.user import User
from src.schemas.auth import AuthResponse, SessionResponse, UserResponse
from src.services.audit_service import log_security_event

settings = get_settings()


async def register_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: str,
    tenant_name: Optional[str] = None,
    ip_address: str = "",
    user_agent: str = "",
) -> AuthResponse:
    """Register a new user and create their primary tenant organization."""
    # Check if email is already taken
    stmt = select(User).where(User.email == email.lower().strip())
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise ValidationException("An account with this email address already exists.")

    # Create new tenant organization
    org_name = tenant_name or f"{full_name.strip()}'s Workspace"
    tenant = Tenant(name=org_name)
    db.add(tenant)
    await db.flush()

    # Create User
    pwd_hash = hash_password(password)
    user = User(
        tenant_id=tenant.id,
        email=email.lower().strip(),
        password_hash=pwd_hash,
        full_name=full_name.strip(),
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    await db.flush()

    # Create Initial Session
    session_expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    session = UserSession(
        user_id=user.id,
        tenant_id=tenant.id,
        user_agent=user_agent[:500],
        ip_address=ip_address[:45],
        expires_at=session_expire,
    )
    db.add(session)
    await db.flush()

    # Create Tokens
    access_token = create_access_token(
        subject=str(user.id),
        tenant_id=str(tenant.id),
        extra_claims={"session_id": str(session.id)},
    )
    raw_refresh_token, refresh_hash = create_refresh_token(
        subject=str(user.id),
        tenant_id=str(tenant.id),
    )

    refresh_token_record = RefreshToken(
        session_id=session.id,
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=session_expire,
    )
    db.add(refresh_token_record)
    await db.flush()

    # Audit Logging
    await log_security_event(
        db=db,
        event_type="registration",
        ip_address=ip_address,
        user_agent=user_agent,
        tenant_id=tenant.id,
        user_id=user.id,
        payload={"email": user.email, "tenant_name": tenant.name},
    )

    return AuthResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


async def login_user(
    db: AsyncSession,
    email: str,
    password: str,
    ip_address: str = "",
    user_agent: str = "",
) -> AuthResponse:
    """Authenticate user with email and password, issuing a new session and token pair."""
    stmt = select(User).where(User.email == email.lower().strip())
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        await log_security_event(
            db=db,
            event_type="failed_login",
            ip_address=ip_address,
            user_agent=user_agent,
            payload={"attempted_email": email},
        )
        raise UnauthorizedException("Invalid email or password.")

    if not user.is_active:
        await log_security_event(
            db=db,
            event_type="login_disabled_account",
            ip_address=ip_address,
            user_agent=user_agent,
            tenant_id=user.tenant_id,
            user_id=user.id,
        )
        raise UnauthorizedException("Your account is currently disabled.")

    # Create Session
    session_expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    session = UserSession(
        user_id=user.id,
        tenant_id=user.tenant_id,
        user_agent=user_agent[:500],
        ip_address=ip_address[:45],
        expires_at=session_expire,
    )
    db.add(session)
    await db.flush()

    # Create Tokens
    access_token = create_access_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
        extra_claims={"session_id": str(session.id)},
    )
    raw_refresh_token, refresh_hash = create_refresh_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
    )

    refresh_record = RefreshToken(
        session_id=session.id,
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=session_expire,
    )
    db.add(refresh_record)
    await db.flush()

    # Log successful login
    await log_security_event(
        db=db,
        event_type="successful_login",
        ip_address=ip_address,
        user_agent=user_agent,
        tenant_id=user.tenant_id,
        user_id=user.id,
        payload={"session_id": str(session.id)},
    )

    return AuthResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


async def rotate_refresh_token(
    db: AsyncSession,
    raw_refresh_token: str,
    ip_address: str = "",
    user_agent: str = "",
) -> AuthResponse:
    """
    Validate and rotate refresh token.
    Detects token reuse: if a used or revoked refresh token is presented,
    the entire session family is instantly revoked for security.
    """
    token_hash = hash_token(raw_refresh_token)
    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    res = await db.execute(stmt)
    token_record = res.scalar_one_or_none()

    if not token_record:
        await log_security_event(
            db=db,
            event_type="token_invalid_attempt",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise UnauthorizedException("Invalid refresh token.")

    session_stmt = select(UserSession).where(UserSession.id == token_record.session_id)
    session_res = await db.execute(session_stmt)
    session = session_res.scalar_one_or_none()

    # --- REUSE DETECTION ---
    if token_record.is_used or token_record.is_revoked or (session and session.is_revoked):
        # Revoke entire session
        if session:
            session.is_revoked = True
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.session_id == session.id)
                .values(is_revoked=True)
            )

        await log_security_event(
            db=db,
            event_type="token_reuse_detected",
            ip_address=ip_address,
            user_agent=user_agent,
            user_id=token_record.user_id,
            tenant_id=session.tenant_id if session else None,
            payload={"session_id": str(token_record.session_id)},
        )
        await db.commit()
        raise UnauthorizedException("Refresh token reuse detected. Session terminated for security.")

    # Check Expiration
    now = datetime.now(timezone.utc)
    token_expires_at = token_record.expires_at
    if token_expires_at.tzinfo is None:
        token_expires_at = token_expires_at.replace(tzinfo=timezone.utc)
    if token_expires_at < now:
        raise UnauthorizedException("Refresh token has expired.")

    # Mark current token as consumed
    token_record.is_used = True
    token_record.is_revoked = True

    # Fetch User
    user_stmt = select(User).where(User.id == token_record.user_id)
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()

    if not user or not user.is_active:
        raise UnauthorizedException("User account is inactive or not found.")

    # Issue New Access Token and New Rotated Refresh Token
    new_access_token = create_access_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
        extra_claims={"session_id": str(session.id)},
    )
    new_raw_refresh, new_refresh_hash = create_refresh_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
    )

    new_refresh_record = RefreshToken(
        session_id=session.id,
        user_id=user.id,
        token_hash=new_refresh_hash,
        expires_at=session.expires_at,
    )
    db.add(new_refresh_record)

    session.last_activity_at = now
    await db.flush()

    await log_security_event(
        db=db,
        event_type="token_refresh",
        ip_address=ip_address,
        user_agent=user_agent,
        tenant_id=user.tenant_id,
        user_id=user.id,
        payload={"session_id": str(session.id)},
    )

    return AuthResponse(
        access_token=new_access_token,
        refresh_token=new_raw_refresh,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


async def logout_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    ip_address: str = "",
    user_agent: str = "",
) -> None:
    """Revoke a specific active user session and all associated refresh tokens."""
    await db.execute(
        update(UserSession)
        .where(UserSession.id == session_id, UserSession.user_id == user_id)
        .values(is_revoked=True)
    )
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.session_id == session_id)
        .values(is_revoked=True)
    )
    await log_security_event(
        db=db,
        event_type="logout",
        ip_address=ip_address,
        user_agent=user_agent,
        tenant_id=tenant_id,
        user_id=user_id,
        payload={"session_id": str(session_id)},
    )


async def logout_all_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    ip_address: str = "",
    user_agent: str = "",
) -> None:
    """Revoke all active sessions and refresh tokens for a user across all devices."""
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id)
        .values(is_revoked=True)
    )
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .values(is_revoked=True)
    )
    await log_security_event(
        db=db,
        event_type="logout_all",
        ip_address=ip_address,
        user_agent=user_agent,
        tenant_id=tenant_id,
        user_id=user_id,
    )


async def list_user_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    current_session_id: Optional[uuid.UUID] = None,
) -> list[SessionResponse]:
    """Retrieve list of active and recent sessions for a user."""
    stmt = (
        select(UserSession)
        .where(UserSession.user_id == user_id)
        .order_by(UserSession.created_at.desc())
    )
    res = await db.execute(stmt)
    sessions = res.scalars().all()

    return [
        SessionResponse(
            id=s.id,
            user_agent=s.user_agent,
            ip_address=s.ip_address,
            is_current=(s.id == current_session_id),
            is_revoked=s.is_revoked,
            created_at=s.created_at,
            last_activity_at=s.last_activity_at,
        )
        for s in sessions
    ]
