# TRADEDNA PRODUCTION DISASTER RECOVERY RUNBOOK
## Operational Continuity, Backup Restoration & Incident Response Protocol

---

## 1. Executive Policy & Golden Invariants

TradeDNA enforces immutable financial integrity across all recovery and business continuity procedures:

1. **Layer 1 Immutability**: Raw deal events and account snapshots are strictly append-only. Recovery procedures must never mutate historical raw observations.
2. **Layer 2 Determinism**: Canonical trades and double-entry postings are reconstructed deterministically from Layer 1 truth.
3. **Zero Financial Drift**: Invariant $\text{Drift} \equiv \$0.00000000$ must be mathematically verified before traffic is restored.
4. **Safety Gates**: Restoration into production is unconditionally blocked if checksum mismatch, schema mismatch, or non-zero drift is detected.
5. **Target Recovery Objectives**:
   - **Target RPO (Recovery Point Objective)**: $\le 5\text{ minutes}$ (Continuous WAL Archiving + Automated Snapshots).
   - **Target RTO (Recovery Time Objective)**: $\le 30\text{ minutes}$ (Measured automated local restoration $\sim 1.25\text{s}$).

---

## 2. Disaster Recovery Scenarios & Playbooks

### Scenario 1: Database Corruption
- **Detection**: Readiness probe `/health/ready` returns HTTP 503; PostgreSQL reports checksum failures or block corruption.
- **Containment**: Stop API container to prevent corrupt state ingestion (`docker compose stop api`).
- **Backup Selection**: Identify latest verified backup archive from `/backups` with status `VERIFIED`.
- **Restore Procedure**:
  1. Provision clean target database volume.
  2. Execute `python scripts/backup_restore.py restore --db-url <URL> --backup-dir backups/YYYY/MM/DD/backup_<timestamp>`.
- **Verification**: Run `verify_backup_archive()` and check exact sum of `realized_net_pnl`.
- **Traffic Recovery**: Restart API and verify `/health/ready` returns HTTP 200.
- **Post-Recovery Checks**: Validate EA reconnection and check for missing historical gaps.
- **Audit**: Log `RESTORE_COMPLETED` audit event with operator user ID and correlation ID.

---

### Scenario 2: Complete Host Failure
- **Detection**: Host instance unreachable; Cloud watchdog triggers instance failover.
- **Containment**: Detach compromised compute instance and isolate network VPC.
- **Backup Selection**: Download latest verified backup from offsite S3-compatible storage.
- **Restore Procedure**: Launch new compute host, pull container images, mount persistent volume, and run restore pipeline.
- **Verification**: Run complete smoke test suite (`python scripts/production_smoke_test.py`).
- **Traffic Recovery**: Update DNS / Load Balancer target group to point to new host IP.
- **Audit**: Record incident duration, measured RTO, and root cause analysis in operational log.

---

### Scenario 3: Container Failure (Crash Loop)
- **Detection**: Docker healthcheck fails 3 consecutive times; container status `unhealthy`.
- **Containment**: Orchestrator isolates container and restarts process with `STOPSIGNAL SIGTERM`.
- **Restore Procedure**: Docker Compose automatically restarts container; database state on persistent volume is untouched.
- **Verification**: Query `/health/live` and `/metrics` to ensure worker processes are active.
- **Traffic Recovery**: Load balancer resumes routing traffic to healthy container replica.

---

### Scenario 4: Bad Deployment (Application Bug)
- **Detection**: HTTP 5xx error spike or frontend exception alarms in `/dashboard/operations`.
- **Containment**: Revert traffic immediately to previous stable Docker image tag (`tradedna-api:previous`).
- **Safety Rule**: Rollback operations **MUST NEVER DROP** Layer 1 or Layer 2 tables.
- **Verification**: Run Phase 9B test suite to confirm backward compatibility.
- **Traffic Recovery**: Verify `/dashboard/overview` loads cleanly for authenticated sessions.

---

### Scenario 5: Failed Migration
- **Detection**: Alembic runner `run_migrations.py` fails with schema conflict or lock timeout.
- **Containment**: Database migration transaction aborts automatically (`transactional DDL`).
- **Restore Procedure**: Re-verify current schema against target head. If corrupted, restore from pre-migration snapshot.
- **Verification**: Run `verify_restoration_integrity()`.

---

### Scenario 6: Accidental Table Deletion
- **Detection**: Readiness check or API query throws `UndefinedTableError`.
- **Containment**: Immediately pause incoming MT5 connector ingress.
- **Restore Procedure**: Execute isolated backup restore into temporary database, extract deleted table, and restore records.
- **Verification**: Verify Layer 1 and Layer 2 record counts against manifest.

---

### Scenario 7: Redis Operational State Loss
- **Detection**: Redis connection error in logs; rate limit and cache fallback triggered.
- **Containment**: Application falls back to local memory rate limiting.
- **Recovery**: Restart Redis container (`docker compose restart redis`).
- **Invariant**: Redis contains **ZERO financial truth**. Cache automatically rebuilds on next requests without data loss.

---

### Scenario 8: Backup File Corruption (Tampering / Bitrot)
- **Detection**: `verify_backup()` fails with `SHA-256 checksum mismatch`.
- **Safety Gate**: Backup marked as `CORRUPTED`. Restore is unconditionally **BLOCKED**.
- **Remediation**: Fallback to immediately prior verified backup archive in chain.

---

### Scenario 9: Multi-Region / Cloud Provider Outage
- **Detection**: Complete regional datacenter outage.
- **Containment**: Activate disaster recovery failover region.
- **Restore Procedure**: Stand up secondary stack using Terraform/Docker, pull backup from multi-region object storage, and apply restore.
- **Traffic Recovery**: Update Global Anycast DNS routing to secondary region.

---

### Scenario 10: Security Incident / Ransomware
- **Detection**: Unauthorized database mutation or cryptographic tampering detected.
- **Containment**: Terminate all active sessions (`logout_all`), revoke all MT5 pairing tokens and device secrets.
- **Restore Procedure**: Wipe compromised database and restore from immutable air-gapped backup snapshot.
- **Verification**: Full security audit and zero-drift verification.
- **Audit**: Log `SECURITY_INCIDENT_RESTORE` with full forensic trace.
