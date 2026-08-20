# TradeDNA Security Architecture & Trust Boundaries

---

## 1. System Overview & Invariants

TradeDNA is an enterprise multi-tenant analytics and financial intelligence platform for Exness MT5 traders. The architecture enforces four non-negotiable security principles:
1. **Strict Read-Only Broker Boundary**: Under no circumstances can TradeDNA initiate, alter, or cancel trades. The system lacks any trade execution primitives (`OrderSend`, `TradeExecute`, etc.).
2. **Immutable Append-Only Ledger**: Layer 1 Raw Observations and Layer 2 Canonical Ledgers cannot be mutated or deleted.
3. **Zero Financial Drift**: Financial reconciliation calculates mathematical truth with exact precision ($\text{Drift} \equiv \$0.00000000$).
4. **Strict Tenant & Account Isolation**: Complete logical partitioning of all stored data, cache keys, telemetry, and background jobs.

---

## 2. Trust Zones & Boundaries

```
 ┌────────────────────────────────────────────────────────┐
 │                     Public Internet                    │
 └─────────────────────────┬──────────────────────────────┘
                           │ TLS 1.3 / HTTPS
                           ▼
 ┌────────────────────────────────────────────────────────┐
 │            Reverse Proxy / Cloudflare Edge             │
 │ - DDoS mitigation                                      │
 │ - Rate limiting & IP reputation                        │
 │ - TLS termination & Security headers                   │
 └─────────────────────────┬──────────────────────────────┘
                           │ Encrypted Internal VPC
                           ▼
 ┌────────────────────────────────────────────────────────┐
 │               TradeDNA API Layer (FastAPI)              │
 │ - JWT verification & RBAC authorization                │
 │ - Multi-tier rate limiting                             │
 │ - Request validation & Sanitization                    │
 │ - Cryptographic HMAC-SHA256 signature verification     │
 └─────────────┬───────────────────────────┬──────────────┘
               │                           │
               ▼                           ▼
 ┌───────────────────────────┐ ┌──────────────────────────┐
 │  PostgreSQL Primary / RO  │ │   Redis Cluster / Cache  │
 │ - Row-level tenant filter │ │ - Isolated cache keys    │
 │ - Encrypted at rest (AES) │ │ - Ephemeral state only   │
 │ - Parameterized queries   │ │ - Non-destructive fallback│
 └───────────────────────────┘ └──────────────────────────┘
```

---

## 3. Defense-in-Depth Control Layers

1. **Edge & Transport**:
   - TLS 1.3 enforcement with HSTS (`max-age=31536000; includeSubDomains; preload`).
   - Hardened Content-Security-Policy (CSP) and frame-ancestors restrictions.
2. **Authentication & Session**:
   - Short-lived JWT access tokens (15m) paired with single-use rotating refresh tokens (30d).
   - HttpOnly, Secure, SameSite=Lax cookies for browser security.
   - Real-time session revocation capability.
3. **Ingress Cryptography**:
   - Nonce-based replay protection with strict timestamp freshness windows ($\pm 300\text{s}$).
   - Symmetric 256-bit HMAC-SHA256 device signatures.
4. **Data & Storage**:
   - Mandatory tenant foreign keys and composite indexes on all domain tables.
   - Deterministic SHA-256 backup manifests and cryptographic checksum verification.
   - Sanitized structured logging suppressing all passwords, tokens, secrets, and connection strings.
