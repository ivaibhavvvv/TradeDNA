import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import jwt
from passlib.context import CryptContext
from src.core.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password securely using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    subject: str,
    tenant_id: str,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """Create a short-lived JWT access token."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "tenant_id": tenant_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(
    subject: str,
    tenant_id: str,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, str]:
    """
    Create a long-lived refresh token.
    Returns (raw_token, token_hash_for_db).
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    raw_token = secrets.token_urlsafe(48)
    token_hash = hash_token(raw_token)
    return raw_token, token_hash


def hash_token(token: str) -> str:
    """Compute SHA-256 hash of a token for secure database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_pairing_token() -> tuple[str, str]:
    """
    Generate a 64-char high-entropy ephemeral pairing token.
    Returns (raw_token, token_hash).
    """
    raw_token = secrets.token_urlsafe(48)  # 64 chars base64url
    token_hash = hash_token(raw_token)
    return raw_token, token_hash


def generate_device_secret() -> str:
    """Generate a 256-bit cryptographically secure secret for HMAC signing."""
    return secrets.token_hex(32)


def compute_hmac_sha256(secret: str, message: str) -> str:
    """Compute HMAC-SHA256 signature for a message payload."""
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_hmac_sha256(secret: str, message: str, expected_signature: str) -> bool:
    """Constant-time verification of HMAC-SHA256 signature."""
    calculated = compute_hmac_sha256(secret, message)
    return hmac.compare_digest(calculated, expected_signature)


def set_auth_cookies(
    response: Any,
    access_token: str,
    refresh_token: str,
) -> None:
    """
    Set production-hardened HttpOnly, Secure, SameSite cookies for authentication.
    - Refresh token cookie path is scoped strictly to /api/v1/auth to prevent leakage.
    - Access token cookie path is scoped to root.
    """
    # 1. Refresh Token Cookie (HttpOnly, scoped to auth path, long-lived)
    response.set_cookie(
        key="tradedna_refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/api/v1/auth",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        domain=settings.COOKIE_DOMAIN,
    )

    # 2. Access Token Cookie (HttpOnly, root path, short-lived)
    response.set_cookie(
        key="tradedna_access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        domain=settings.COOKIE_DOMAIN,
    )


def clear_auth_cookies(response: Any) -> None:
    """Clear and invalidate all authentication cookies."""
    response.delete_cookie(
        key="tradedna_refresh_token",
        path="/api/v1/auth",
        domain=settings.COOKIE_DOMAIN,
    )
    response.delete_cookie(
        key="tradedna_access_token",
        path="/",
        domain=settings.COOKIE_DOMAIN,
    )

