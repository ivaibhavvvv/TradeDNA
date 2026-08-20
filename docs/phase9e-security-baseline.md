# TRADEDNA — PHASE 9E SECURITY BASELINE AUDIT
## Production Security, Penetration Testing & Compliance Hardening

**Date**: 2026-08-19  
**Phase**: Phase 9E  
**Status**: **BASELINE ESTABLISHED**  

---

## 1. Authentication Architecture & Token Security

- **Password Hashing**: Industry-standard `bcrypt` algorithm with automated work-factor management via `passlib.context.CryptContext(schemes=["bcrypt"])`.
- **JWT Access Tokens**:
  - Algorithm: `HS256` (Configurable via `JWT_ALGORITHM`).
  - Claims: `sub` (User UUID), `tenant_id` (Tenant UUID), `session_id` (Session UUID), `type="access"`, `iat`, `exp`.
  - Expiry: 15 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES = 15`).
  - Signature & Algorithm Confusion Defense: Verified strictly against server-side secret key with explicit algorithm restriction in `jwt.decode(..., algorithms=[settings.JWT_ALGORITHM])`.
- **Refresh Tokens**:
  - Generation: Cryptographically secure 256-bit entropy (`secrets.token_urlsafe(48)`).
  - Storage: Stored only as SHA-256 hash (`hash_token`) in `user_sessions` / `refresh_tokens` tables.
  - Rotation: Single-use rotation on each refresh; previous token hash is revoked immediately.
  - Revocation & Session Invalidation: Eager DB session verification in `get_current_user` rejects revoked sessions in real-time.

---

## 2. Cookie Security Configuration

- **Cookies Configured**:
  - `tradedna_access_token`: `HttpOnly=True`, `Secure=True` (in production/HTTPS), `SameSite="lax"`, `Path="/"`, `max_age=900s`.
  - `tradedna_refresh_token`: `HttpOnly=True`, `Secure=True` (in production/HTTPS), `SameSite="lax"`, `Path="/api/v1/auth"`, `max_age=30 days`.
- **Mitigations**:
  - `HttpOnly` flag prevents direct JavaScript DOM access (mitigating XSS session theft).
  - Path scoping on the refresh cookie (`/api/v1/auth`) restricts transmission strictly to token refresh/logout endpoints.
  - SameSite policy prevents cross-origin cookie attachment during unauthorized third-party requests.

---

## 3. Multi-Tenant & Multi-Account Isolation Architecture

- **Tenant Isolation**:
  - Database-level `tenant_id` foreign keys on all Layer 1, Layer 2, Layer 3, and configuration tables.
  - Mandatory tenant resolution in `get_current_user` and `enforce_tenant_isolation(resource_tenant_id, current_user)`.
  - All repository queries explicitly filter by `where(Model.tenant_id == current_user.tenant_id)`.
  - Cache keys prefixed with `cache:{tenant_id}:{account_id}:...`.
- **Account Isolation**:
  - User can only query accounts registered to their specific tenant (`_resolve_sync_state`).
  - Stale cache purging and request abort controllers decouple client-side state during rapid account switching.

---

## 4. API Ingress, HMAC & Terminal Authentication

- **Pairing Flow**:
  - Ephemeral single-use pairing token (64-character base64url, 15-minute TTL, SHA-256 hashed in database).
  - Device provisioning issues a unique 256-bit symmetric `device_secret`.
- **HMAC Verification**:
  - MT5 terminal signs payload using `HMAC-SHA256(device_secret, canonical_message)`.
  - Canonical message incorporates `timestamp_msc`, `device_id`, and `nonce`.
  - Anti-Replay: Nonce tracking with timestamp freshness window ($\pm 300\text{ seconds}$).
  - Device Revocation: 1-click device revocation immediately sets `is_revoked=True`, terminating ingress validation in constant time.

---

## 5. Security Headers, CORS & Rate Limiting

- **HTTP Security Headers**:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: geolocation=(), camera=(), microphone=(), payment=()`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
  - `Content-Security-Policy`: Production CSP restricting `script-src`, `connect-src`, and blocking `object-src`/`frame-ancestors`.
- **CORS Configuration**:
  - Explicit allowlist matching trusted frontend origins (no `allow_origins=["*"]` when credentials are enabled).
- **Multi-Tier Rate Limiting**:
  - `AUTH`: 5 requests / 60 seconds (brute-force protection).
  - `PAIRING`: 10 requests / 60 seconds.
  - `INGRESS`: 1,000 requests / 60 seconds.
  - `DASHBOARD`: 120 requests / 60 seconds.

---

## 6. Input Validation, Injection Defense & Sanitization

- **SQL Injection**: Exclusively parameterized SQLAlchemy 2.0 ORM and Core statements with typed parameters. Zero raw string interpolation.
- **Command / OS Injection**: Zero direct `os.system()` or unsanitized shell invocations with user input.
- **Path Traversal**: File operations use strictly validated UUID identifiers and sanitizing `os.path.basename` / `os.path.abspath` resolution within isolated directory trees.
- **XSS**: React JSX automatically escapes dynamic values; FastAPI sanitizes Pydantic input schemas.
- **SSRF**: API performs zero outbound HTTP requests to user-supplied URLs.
- **Error Sanitization**: Global exception handlers strip internal database parameters, connection strings, tracebacks, and secrets from JSON responses.
