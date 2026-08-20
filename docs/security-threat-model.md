# TradeDNA Security Threat Model & STRIDE Assessment

---

## 1. Threat Actors & Capabilities

| Threat Actor | Motivation | Capabilities | Target Assets |
| :--- | :--- | :--- | :--- |
| **External Attacker** | Data theft, disruption | Credential stuffing, DDoS, injection, SSRF, replay | User accounts, API bandwidth, database |
| **Malicious Authenticated User** | Cross-tenant espionage | IDOR / BOLA, account switching race conditions | Other tenants' trading data & analytics |
| **Compromised MT5 Terminal** | Ingress disruption, spoofing | Forged deals, rapid replay, invalid timestamps | Raw observation pipeline, system capacity |
| **Insider / Rogue Admin** | Unauthorized data access | Privilege escalation, backup manipulation | Financial ledgers, database snapshots |
| **Supply Chain Attacker** | Code tampering | Compromised npm / PyPI packages | Backend API, frontend client bundle |

---

## 2. STRIDE Assessment & Mitigations

### S — Spoofing Identity
- **Threat**: Forging MT5 terminal events or masquerading as another user.
- **Mitigation**: Symmetric HMAC-SHA256 device signing with unique per-device 256-bit secrets; ephemeral 15-minute pairing tokens; JWT signature verification with HS256 key.

### T — Tampering with Data
- **Threat**: Modifying raw observations, canonical trades, or backup manifests.
- **Mitigation**: Database immutability triggers and rules on Layer 1 & Layer 2 tables; deterministic SHA-256 backup manifests and financial checksum verification.

### R — Repudiation
- **Threat**: User denies performing critical operations (e.g. device revocation, backup restore).
- **Mitigation**: Comprehensive append-only structured audit logs (`audit_logs`) tracking `user_id`, `action`, `client_ip`, `user_agent`, and `timestamp_utc`.

### I — Information Disclosure
- **Threat**: Leaking PII, financial ledgers, or database credentials via error responses or logs.
- **Mitigation**: Global exception handlers sanitize all tracebacks and parameters; Phase 9B logger redacts passwords, tokens, secrets, and database URLs.

### D — Denial of Service
- **Threat**: Exhausting database connection pools or API workers through high-rate requests.
- **Mitigation**: Multi-tier token-bucket rate limiting (`AUTH`, `PAIRING`, `INGRESS`, `DASHBOARD`); bounded backpressure queues; async connection pooling.

### E — Elevation of Privilege
- **Threat**: Regular user invoking administrative or backup restoration endpoints.
- **Mitigation**: Strict role-based access control (RBAC) and explicit role verification (`current_user.role == "ADMIN"`).
