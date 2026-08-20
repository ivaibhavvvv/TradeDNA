# TradeDNA Phase 9E Security Hardening & Compliance Checklist

---

## 1. Hardening Actions Applied

- [x] **Cookie Hardening**: Scoped refresh token cookie path to `/api/v1/auth`, enforced `HttpOnly`, `SameSite=Lax`, and `Secure` flags.
- [x] **JWT Algorithm Whitelisting**: Strict algorithm binding (`HS256`) during decode to prevent algorithm confusion attacks (`alg=none`, `RS256` key confusion).
- [x] **Multi-Tenant Boundary Enforcement**: Explicit `enforce_tenant_isolation` check and row-level tenant filtering on all repository queries.
- [x] **Anti-Replay Nonce Validation**: Monotonic timestamp freshness ($\pm 300\text{s}$) and unique nonce registration for HMAC device communication.
- [x] **Error Response Sanitization**: Global exception handlers prevent leaking stack traces, internal paths, SQL queries, or credentials.
- [x] **Structured Log Redaction**: Automatic pattern-based redaction of passwords, tokens, device secrets, and database connection strings.
- [x] **Container Security**: Non-root runtime user execution, minimal base image footprints, and zero baked-in secrets.
- [x] **Static MT5 Invariant Guard**: Continuous verification of zero trade execution primitives (`OrderSend`, `Trade.mqh`, etc.).

---

## 2. Residual Risk & Ongoing Monitoring

- **Dependency Vulnerability Management**: Daily automated Dependabot / audit scans to detect newly disclosed CVEs in npm and PyPI packages.
- **Session Revocation Latency**: Real-time database checks ensure session revocation takes effect instantly without waiting for JWT expiration.
- **Financial Immutability**: Nightly reconciliation runs verify zero drift across all active accounts.
