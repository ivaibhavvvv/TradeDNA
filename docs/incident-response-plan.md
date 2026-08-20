# TradeDNA Security Incident Response Plan (IRP)

---

## 1. Incident Severity Levels

| Level | Classification | Examples | Initial Response SLA |
| :--- | :--- | :--- | :--- |
| **SEV-1 (Critical)** | Active Data Breach, Zero-Day Exploit, Financial Drift $> \$0.00$ | Cross-tenant leakage, unauthorized database dump, ledger corruption | $< 15\text{ minutes}$ |
| **SEV-2 (High)** | Impaired Isolation, Authentication Failure, Service Degradation | Rate-limit failure under attack, HMAC replay vulnerability, worker crash loop | $< 60\text{ minutes}$ |
| **SEV-3 (Medium)** | Non-Exploitable Bug, Minor Audit Anomaly | Suspicious login spikes, malformed ingress format, stale cache glitch | $< 4\text{ hours}$ |
| **SEV-4 (Low)** | Informational Alert, Cosmetic Finding | Dependency update warning, low-impact documentation discrepancy | $< 24\text{ hours}$ |

---

## 2. Six-Phase Incident Response Lifecycle

1. **Preparation**:
   - Centralized logging with automated redaction.
   - Real-time Prometheus metrics tracking authentication failures and anomalous rate-limit spikes.
2. **Identification & Triaging**:
   - Automated detection triggers operational alerts (`SEV-1`/`SEV-2`).
   - Incident Commander (IC) assesses blast radius and assigns triage tickets.
3. **Containment**:
   - **Short-Term**: 1-click device revocation (`/connections/devices/{device_id}/revoke`), global user session revocation (`/auth/logout-all`), or dynamic IP throttling at reverse proxy.
   - **Long-Term**: Isolation of affected database replicas or maintenance mode enablement.
4. **Eradication**:
   - Patch underlying code vulnerability or rotate compromised secrets (JWT secret, DB passwords, S3 keys).
   - Invalidate all issued pairing tokens and active sessions.
5. **Recovery**:
   - Validate financial ledger immutability and execute `run_reconciliation_check` across all golden accounts.
   - If database restore is required, follow the Disaster Recovery Runbook with cryptographic checksum validation.
6. **Post-Incident Analysis & Forensics**:
   - Preserve immutable audit logs and generate Root Cause Analysis (RCA) report within 48 hours.
