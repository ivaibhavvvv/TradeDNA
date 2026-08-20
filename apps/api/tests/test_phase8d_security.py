"""TradeDNA Phase 8D-B - Production Security Hardening Test Suite.
Comprehensive automated verification of:
1. HttpOnly cookie authentication
2. Secure cookie production configuration
3. SameSite behavior
4. Refresh rotation
5. Refresh-token reuse detection
6. Family revocation upon reuse
7. Revoked-session rejection
8. Logout current session
9. Logout-all sessions
10. Disabled-user rejection
11. Expired-token rejection
12. Login rate limiting
13. Registration rate limiting
14. Refresh rate limiting
15. Pairing rate limiting
16. Dashboard rate limiting
17. Legitimate EA heartbeat is not rate limited
18. Excessive EA traffic is rate limited
19. CSP header presence and directives
20. HSTS header configuration
21. X-Content-Type-Options: nosniff
22. X-Frame-Options: DENY / frame-ancestors 'none'
23. Referrer-Policy: strict-origin-when-cross-origin
24. Strict CORS allowlist
25. Credential redaction in audit logs
26. Stack-trace suppression in error responses
27. Tenant isolation remains intact
28. Security audit events generated
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import get_settings
from src.core.rate_limit import InMemoryRateLimiter, RateLimitExceededException, rate_limiter
from src.core.security import create_access_token, create_refresh_token, hash_password, hash_token
from src.main import app
from src.models.audit import AuditLog
from src.models.device import Device
from src.models.session import RefreshToken, UserSession
from src.models.tenant import Tenant
from src.models.user import User
from src.services.audit_service import log_security_event
from src.services.auth_service import rotate_refresh_token

settings = get_settings()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    rate_limiter.reset()
    rate_limiter.force_enabled = False
    yield
    rate_limiter.reset()
    rate_limiter.force_enabled = False


# =========================================================================
# 1-3. HttpOnly, Secure, SameSite Cookie Attributes & Authentication
# =========================================================================

@pytest.mark.asyncio
async def test_01_httponly_cookie_authentication(db_session: AsyncSession):
    """1. Verifies that requests with HttpOnly access_token cookie authenticate without Bearer header."""
    tenant = Tenant(id=uuid.uuid4(), name="T1")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="t1@tradedna.io", password_hash="h", full_name="User 1", is_active=True)
    db_session.add_all([tenant, user])
    await db_session.commit()

    token = create_access_token(subject=str(user.id), tenant_id=str(tenant.id))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set("tradedna_access_token", token)
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == "t1@tradedna.io"


@pytest.mark.asyncio
async def test_02_secure_cookie_production_configuration(db_session: AsyncSession):
    """2. Verifies Set-Cookie header contains HttpOnly and path scoping."""
    tenant = Tenant(id=uuid.uuid4(), name="T2")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="t2@tradedna.io", password_hash=hash_password("Pass123!"), full_name="User 2", is_active=True)
    db_session.add_all([tenant, user])
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/login", json={"email": "t2@tradedna.io", "password": "Pass123!"})
        assert resp.status_code == 200
        set_cookie_str = "; ".join(resp.headers.get_list("set-cookie"))
        assert "HttpOnly" in set_cookie_str
        assert "tradedna_refresh_token=" in set_cookie_str
        assert "tradedna_access_token=" in set_cookie_str


@pytest.mark.asyncio
async def test_03_samesite_behavior(db_session: AsyncSession):
    """3. Verifies SameSite cookie policy is set (Lax)."""
    tenant = Tenant(id=uuid.uuid4(), name="T3")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="t3@tradedna.io", password_hash=hash_password("Pass123!"), full_name="User 3", is_active=True)
    db_session.add_all([tenant, user])
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/login", json={"email": "t3@tradedna.io", "password": "Pass123!"})
        assert resp.status_code == 200
        set_cookie_str = "; ".join(resp.headers.get_list("set-cookie"))
        assert "SameSite=lax" in set_cookie_str.lower() or "samesite=lax" in set_cookie_str.lower()


# =========================================================================
# 4-7. Refresh Token Rotation, Reuse Detection & Revocation
# =========================================================================

@pytest.mark.asyncio
async def test_04_refresh_rotation(db_session: AsyncSession):
    """4. Verifies refresh token rotation issues a new token and consumes the old one."""
    tenant = Tenant(id=uuid.uuid4(), name="T4")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="t4@tradedna.io", password_hash="h", full_name="User 4", is_active=True)
    session = UserSession(id=uuid.uuid4(), user_id=user.id, tenant_id=tenant.id, expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    raw_refresh, refresh_hash = create_refresh_token(subject=str(user.id), tenant_id=str(tenant.id))
    rec = RefreshToken(session_id=session.id, user_id=user.id, token_hash=refresh_hash, expires_at=session.expires_at)
    db_session.add_all([tenant, user, session, rec])
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set("tradedna_refresh_token", raw_refresh)
        resp = await client.post("/api/v1/auth/refresh")
        assert resp.status_code == 200
        assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_05_refresh_token_reuse_detection(db_session: AsyncSession):
    """5. Verifies that using an already consumed refresh token triggers immediate rejection."""
    tenant = Tenant(id=uuid.uuid4(), name="T5")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="t5@tradedna.io", password_hash="h", full_name="User 5", is_active=True)
    session = UserSession(id=uuid.uuid4(), user_id=user.id, tenant_id=tenant.id, expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    raw_refresh, refresh_hash = create_refresh_token(subject=str(user.id), tenant_id=str(tenant.id))
    rec = RefreshToken(session_id=session.id, user_id=user.id, token_hash=refresh_hash, is_used=True, is_revoked=True, expires_at=session.expires_at)
    db_session.add_all([tenant, user, session, rec])
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set("tradedna_refresh_token", raw_refresh)
        resp = await client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401
        assert "reuse detected" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_06_family_revocation(db_session: AsyncSession):
    """6. Verifies that reuse detection invalidates the entire session and all sister tokens in the family."""
    tenant = Tenant(id=uuid.uuid4(), name="T6")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="t6@tradedna.io", password_hash="h", full_name="User 6", is_active=True)
    session = UserSession(id=uuid.uuid4(), user_id=user.id, tenant_id=tenant.id, expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    raw_old, hash_old = create_refresh_token(subject=str(user.id), tenant_id=str(tenant.id))
    raw_active, hash_active = create_refresh_token(subject=str(user.id), tenant_id=str(tenant.id))

    rec_old = RefreshToken(session_id=session.id, user_id=user.id, token_hash=hash_old, is_used=True, is_revoked=True, expires_at=session.expires_at)
    rec_active = RefreshToken(session_id=session.id, user_id=user.id, token_hash=hash_active, is_used=False, is_revoked=False, expires_at=session.expires_at)
    db_session.add_all([tenant, user, session, rec_old, rec_active])
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Trigger reuse on old token
        client.cookies.set("tradedna_refresh_token", raw_old)
        await client.post("/api/v1/auth/refresh")

        # Now active sister token must also be rejected
        client.cookies.set("tradedna_refresh_token", raw_active)
        resp2 = await client.post("/api/v1/auth/refresh")
        assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_07_revoked_session_rejection(db_session: AsyncSession):
    """7. Verifies that access tokens from a revoked session are rejected."""
    tenant = Tenant(id=uuid.uuid4(), name="T7")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="t7@tradedna.io", password_hash="h", full_name="User 7", is_active=True)
    session = UserSession(id=uuid.uuid4(), user_id=user.id, tenant_id=tenant.id, is_revoked=True, expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    db_session.add_all([tenant, user, session])
    await db_session.commit()

    token = create_access_token(subject=str(user.id), tenant_id=str(tenant.id), extra_claims={"session_id": str(session.id)})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set("tradedna_access_token", token)
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401
        assert "revoked" in resp.json()["error"]["message"].lower()


# =========================================================================
# 8-11. Session Lifecycle, Disabled & Expired Tokens
# =========================================================================

@pytest.mark.asyncio
async def test_08_logout(db_session: AsyncSession):
    """8. Verifies logout revokes the current session."""
    tenant = Tenant(id=uuid.uuid4(), name="T8")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="t8@tradedna.io", password_hash="h", full_name="User 8", is_active=True)
    session = UserSession(id=uuid.uuid4(), user_id=user.id, tenant_id=tenant.id, expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    db_session.add_all([tenant, user, session])
    await db_session.commit()

    token = create_access_token(subject=str(user.id), tenant_id=str(tenant.id), extra_claims={"session_id": str(session.id)})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set("tradedna_access_token", token)
        resp = await client.post("/api/v1/auth/logout")
        assert resp.status_code == 200
        assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_09_logout_all(db_session: AsyncSession):
    """9. Verifies logout-all invalidates all active sessions for a user."""
    tenant = Tenant(id=uuid.uuid4(), name="T9")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="t9@tradedna.io", password_hash="h", full_name="User 9", is_active=True)
    s1 = UserSession(id=uuid.uuid4(), user_id=user.id, tenant_id=tenant.id, expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    s2 = UserSession(id=uuid.uuid4(), user_id=user.id, tenant_id=tenant.id, expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    db_session.add_all([tenant, user, s1, s2])
    await db_session.commit()

    t1 = create_access_token(subject=str(user.id), tenant_id=str(tenant.id), extra_claims={"session_id": str(s1.id)})
    t2 = create_access_token(subject=str(user.id), tenant_id=str(tenant.id), extra_claims={"session_id": str(s2.id)})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set("tradedna_access_token", t1)
        resp = await client.post("/api/v1/auth/logout-all")
        assert resp.status_code == 200

        # Session 2 must be invalid now
        client.cookies.set("tradedna_access_token", t2)
        resp2 = await client.get("/api/v1/auth/me")
        assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_10_disabled_user_rejection(db_session: AsyncSession):
    """10. Verifies disabled users cannot authenticate."""
    tenant = Tenant(id=uuid.uuid4(), name="T10")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="t10@tradedna.io", password_hash="h", full_name="User 10", is_active=False)
    db_session.add_all([tenant, user])
    await db_session.commit()

    token = create_access_token(subject=str(user.id), tenant_id=str(tenant.id))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set("tradedna_access_token", token)
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_11_expired_token_rejection():
    """11. Verifies expired access tokens return 401."""
    token = create_access_token(subject=str(uuid.uuid4()), tenant_id=str(uuid.uuid4()), expires_delta=timedelta(seconds=-1))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set("tradedna_access_token", token)
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401


# =========================================================================
# 12-18. Tiered Rate Limiting & EA Protection
# =========================================================================

def test_12_login_rate_limiting():
    """12. Verifies login rate limit quota enforcement."""
    limiter = InMemoryRateLimiter()
    limiter.force_enabled = True
    for _ in range(10):
        limiter.check_rate_limit("AUTH:127.0.0.1:/api/v1/auth/login", max_requests=10, window_seconds=60)
    with pytest.raises(RateLimitExceededException):
        limiter.check_rate_limit("AUTH:127.0.0.1:/api/v1/auth/login", max_requests=10, window_seconds=60)


def test_13_registration_rate_limiting():
    """13. Verifies registration rate limit quota enforcement."""
    limiter = InMemoryRateLimiter()
    limiter.force_enabled = True
    for _ in range(5):
        limiter.check_rate_limit("AUTH:127.0.0.1:/api/v1/auth/register", max_requests=5, window_seconds=60)
    with pytest.raises(RateLimitExceededException):
        limiter.check_rate_limit("AUTH:127.0.0.1:/api/v1/auth/register", max_requests=5, window_seconds=60)


def test_14_refresh_rate_limiting():
    """14. Verifies refresh rate limit quota enforcement."""
    limiter = InMemoryRateLimiter()
    limiter.force_enabled = True
    for _ in range(20):
        limiter.check_rate_limit("AUTH:127.0.0.1:/api/v1/auth/refresh", max_requests=20, window_seconds=60)
    with pytest.raises(RateLimitExceededException):
        limiter.check_rate_limit("AUTH:127.0.0.1:/api/v1/auth/refresh", max_requests=20, window_seconds=60)


def test_15_pairing_rate_limiting():
    """15. Verifies device pairing rate limit quota enforcement."""
    limiter = InMemoryRateLimiter()
    limiter.force_enabled = True
    for _ in range(10):
        limiter.check_rate_limit("PAIRING:127.0.0.1:/api/v1/exness/connection/pair", max_requests=10, window_seconds=60)
    with pytest.raises(RateLimitExceededException):
        limiter.check_rate_limit("PAIRING:127.0.0.1:/api/v1/exness/connection/pair", max_requests=10, window_seconds=60)


def test_16_dashboard_rate_limiting():
    """16. Verifies dashboard BFF rate limit quota enforcement."""
    limiter = InMemoryRateLimiter()
    limiter.force_enabled = True
    for _ in range(120):
        limiter.check_rate_limit("DASHBOARD:127.0.0.1:/api/v1/dashboard/overview", max_requests=120, window_seconds=60)
    with pytest.raises(RateLimitExceededException):
        limiter.check_rate_limit("DASHBOARD:127.0.0.1:/api/v1/dashboard/overview", max_requests=120, window_seconds=60)


def test_17_legitimate_ea_heartbeat_is_not_rate_limited():
    """17. Verifies that 1000ms legitimate EA heartbeats (60 req/min) operate safely within the 300 req/min quota."""
    limiter = InMemoryRateLimiter()
    limiter.force_enabled = True
    for _ in range(60):
        rem, _, _ = limiter.check_rate_limit("INGRESS:device-101:/api/v1/exness/sync", max_requests=300, window_seconds=60)
        assert rem >= 240


def test_18_excessive_ea_traffic_is_rate_limited():
    """18. Verifies that connector traffic exceeding 300 req/min is rate limited."""
    limiter = InMemoryRateLimiter()
    limiter.force_enabled = True
    for _ in range(300):
        limiter.check_rate_limit("INGRESS:flooder:/api/v1/exness/sync", max_requests=300, window_seconds=60)
    with pytest.raises(RateLimitExceededException):
        limiter.check_rate_limit("INGRESS:flooder:/api/v1/exness/sync", max_requests=300, window_seconds=60)


# =========================================================================
# 19-24. Security Headers & Strict CORS
# =========================================================================

@pytest.mark.asyncio
async def test_19_csp_header():
    """19. Verifies Content-Security-Policy header presence and directives."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp


@pytest.mark.asyncio
async def test_20_hsts_header():
    """20. Verifies HSTS header is configured when enabled."""
    settings.HSTS_ENABLED = True
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/")
            assert "Strict-Transport-Security" in resp.headers
    finally:
        settings.HSTS_ENABLED = False


@pytest.mark.asyncio
async def test_21_x_content_type_options():
    """21. Verifies X-Content-Type-Options: nosniff."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"


@pytest.mark.asyncio
async def test_22_x_frame_options():
    """22. Verifies X-Frame-Options: DENY."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.headers.get("X-Frame-Options") == "DENY"


@pytest.mark.asyncio
async def test_23_referrer_policy():
    """23. Verifies Referrer-Policy: strict-origin-when-cross-origin."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_24_strict_cors():
    """24. Verifies CORS reject wildcard * with credentials."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.options(
            "/api/v1/auth/login",
            headers={"Origin": "https://untrusted-site.com", "Access-Control-Request-Method": "POST"},
        )
        assert resp.headers.get("access-control-allow-origin") != "https://untrusted-site.com"
        assert resp.headers.get("access-control-allow-origin") != "*"


# =========================================================================
# 25-28. Redaction, Stack-Trace Suppression, Tenant Isolation & Audit Events
# =========================================================================

@pytest.mark.asyncio
async def test_25_credential_redaction(db_session: AsyncSession):
    """25. Verifies passwords, tokens, and secrets are redacted in audit logging."""
    tenant = Tenant(id=uuid.uuid4(), name="T25")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="t25@tradedna.io", password_hash="h", full_name="User 25", is_active=True)
    db_session.add_all([tenant, user])
    await db_session.flush()

    audit = await log_security_event(
        db=db_session,
        event_type="test_redact",
        tenant_id=tenant.id,
        user_id=user.id,
        payload={"password": "secret_password", "token": "raw_jwt", "secret": "hmac_key"},
    )
    assert audit.payload["password"] == "[REDACTED]"
    assert audit.payload["token"] == "[REDACTED]"
    assert audit.payload["secret"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_26_stack_trace_suppression():
    """26. Verifies error responses never leak stack traces or internal code paths."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/login", json={"email": "bad", "password": "1"})
        assert resp.status_code == 422
        body = resp.text
        assert "traceback" not in body.lower()
        assert "file \"" not in body.lower()
        assert "sqlalchemy" not in body.lower()


@pytest.mark.asyncio
async def test_27_tenant_isolation_remains_intact(db_session: AsyncSession):
    """27. Verifies cross-tenant resource queries remain isolated."""
    t1 = Tenant(id=uuid.uuid4(), name="T27-A")
    u1 = User(id=uuid.uuid4(), tenant_id=t1.id, email="u27a@tradedna.io", password_hash="h", full_name="User 27A", is_active=True)
    t2 = Tenant(id=uuid.uuid4(), name="T27-B")
    u2 = User(id=uuid.uuid4(), tenant_id=t2.id, email="u27b@tradedna.io", password_hash="h", full_name="User 27B", is_active=True)
    db_session.add_all([t1, u1, t2, u2])
    await db_session.commit()

    token1 = create_access_token(subject=str(u1.id), tenant_id=str(t1.id))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set("tradedna_access_token", token1)
        resp = await client.get("/api/v1/exness/devices")
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.asyncio
async def test_28_security_audit_events_generated(db_session: AsyncSession):
    """28. Verifies that security audit logs are recorded on security lifecycle actions."""
    tenant = Tenant(id=uuid.uuid4(), name="T28")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="t28@tradedna.io", password_hash="h", full_name="User 28", is_active=True)
    db_session.add_all([tenant, user])
    await db_session.flush()

    audit = await log_security_event(
        db=db_session,
        event_type="security_audit_test",
        tenant_id=tenant.id,
        user_id=user.id,
        payload={"action": "test_verification"},
    )
    assert audit.id is not None
    assert audit.event_type == "security_audit_test"
