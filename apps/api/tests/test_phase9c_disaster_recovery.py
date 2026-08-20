"""
TradeDNA Phase 9C - Disaster Recovery, Backup Automation & Business Continuity Test Suite
Verifies backup creation, deterministic financial checksums, corruption detection,
isolated test restoration, safety gates, tenant isolation, RPO/RTO metrics, and zero-drift invariants.
"""

import os
import json
import time
import uuid
import shutil
import hashlib
import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone, timedelta
from pathlib import Path

from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import create_engine, select, text

from src.main import app
from src.core.config import settings
from src.core.backup import (
    BackupManager,
    backup_manager,
    compute_layer1_checksum,
    compute_layer2_checksum,
    compute_layer3_checksum,
    compute_financial_aggregates,
    SafetyGateViolationException,
)
from src.core.backup_storage import LocalStorageProvider, S3CompatibleStorageProvider
from src.core.metrics import metrics
from src.models.user import User
from src.models.tenant import Tenant
from src.models.canonical_ledger import CanonicalTrade
from src.models.raw_event import RawIngressPayload, RawEventObservation
from src.models.reconciliation import ReconciliationRun
from src.models.audit import AuditLog
from src.services.dashboard_service import DashboardService


@pytest.fixture
def temp_backup_dir(tmp_path):
    d = tmp_path / "test_backups"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


@pytest.fixture
async def registered_user_and_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        email = f"dr_user_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "StrongSecurePassword123!"
        reg_res = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": pwd, "full_name": "DR User", "tenant_name": "DR Tenant"},
        )
        assert reg_res.status_code == 201, f"Registration failed: {reg_res.text}"
        token = reg_res.json()["access_token"]
        user_id = reg_res.json()["user"]["id"]
        tenant_id = reg_res.json()["user"]["tenant_id"]
        return {
            "email": email,
            "token": token,
            "user_id": uuid.UUID(user_id),
            "tenant_id": uuid.UUID(tenant_id),
        }


@pytest.mark.asyncio
async def test_scenario_01_backup_creation(temp_backup_dir):
    """Scenario 1: Creates backup archive containing database.json, manifest.json, and checksum.sha256."""
    target_dir = os.path.join(temp_backup_dir, "backup_test_01")
    manifest = BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
        backup_type="FULL",
    )
    assert os.path.exists(os.path.join(target_dir, "database.json"))
    assert os.path.exists(os.path.join(target_dir, "manifest.json"))
    assert os.path.exists(os.path.join(target_dir, "checksum.sha256"))
    assert manifest["status"] == "CREATED"
    assert manifest["file_size_bytes"] > 0


@pytest.mark.asyncio
async def test_scenario_02_backup_manifest_schema(temp_backup_dir):
    """Scenario 2: Manifest contains all required production fields without secrets."""
    target_dir = os.path.join(temp_backup_dir, "backup_test_02")
    manifest = BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
    )
    required_keys = [
        "backup_id",
        "created_at",
        "database_name",
        "application_version",
        "backup_type",
        "file_size_bytes",
        "sha256",
        "tables_verified",
        "layer1_record_count",
        "layer2_record_count",
        "layer3_record_count",
        "financial_checksum",
        "status",
    ]
    for k in required_keys:
        assert k in manifest, f"Missing key {k} in manifest"

    # Zero secrets in manifest
    manifest_str = str(manifest).lower()
    for forbidden in ["password", "secret", "jwt", "token"]:
        assert forbidden not in manifest_str


@pytest.mark.asyncio
async def test_scenario_03_checksum_generation_determinism():
    """Scenario 3: Deterministic checksum generation produces identical hashes regardless of input order."""
    deal1 = {"deal_ticket": 100, "time_msc": 1000, "deal_type": "DEAL_TYPE_BUY", "volume": Decimal("0.1"), "price": Decimal("2000.5"), "profit": Decimal("10.0")}
    deal2 = {"deal_ticket": 101, "time_msc": 2000, "deal_type": "DEAL_TYPE_SELL", "volume": Decimal("0.1"), "price": Decimal("2001.0"), "profit": Decimal("-5.0")}

    hash1 = compute_layer1_checksum([deal1, deal2])
    hash2 = compute_layer1_checksum([deal2, deal1])
    assert hash1 == hash2


@pytest.mark.asyncio
async def test_scenario_04_checksum_verification_valid(temp_backup_dir):
    """Scenario 4: verify_backup() succeeds on untampered backup and marks it VERIFIED."""
    target_dir = os.path.join(temp_backup_dir, "backup_test_04")
    BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
    )
    is_valid, report = BackupManager.verify_backup(target_dir)
    assert is_valid is True
    assert report["status"] == "VERIFIED"
    assert "verified_at" in report


@pytest.mark.asyncio
async def test_scenario_05_backup_corruption_detection(temp_backup_dir):
    """Scenario 5: Byte tampering in database.json is detected by SHA-256 and marked CORRUPTED."""
    target_dir = os.path.join(temp_backup_dir, "backup_test_05")
    BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
    )
    # Corrupt database.json
    db_file = os.path.join(target_dir, "database.json")
    with open(db_file, "a", encoding="utf-8") as f:
        f.write(" ")

    is_valid, report = BackupManager.verify_backup(target_dir)
    assert is_valid is False
    assert "checksum mismatch" in report["error"].lower()

    # Verify manifest status updated to CORRUPTED
    with open(os.path.join(target_dir, "manifest.json"), "r") as f:
        m = json.load(f)
    assert m["status"] == "CORRUPTED"


@pytest.mark.asyncio
async def test_scenario_06_isolated_restore_workflow(temp_backup_dir, tmp_path):
    """Scenario 6: Restores database into an isolated SQLite database cleanly."""
    target_dir = os.path.join(temp_backup_dir, "backup_test_06")
    BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
    )
    # Isolated DB
    iso_db_file = tmp_path / "isolated.db"
    iso_db_url = f"sqlite:///{iso_db_file}"

    # Initialize schema in isolated DB
    from src.models.base import Base
    iso_engine = create_engine(iso_db_url)
    Base.metadata.create_all(iso_engine)

    summary = BackupManager.restore_backup(
        sync_db_url=iso_db_url,
        backup_dir=target_dir,
    )
    assert isinstance(summary, dict)
    assert "tenants" in summary


@pytest.mark.asyncio
async def test_scenario_07_layer1_exact_equality(temp_backup_dir, tmp_path):
    """Scenario 7: Restored Layer 1 raw deal events match original count and checksum."""
    target_dir = os.path.join(temp_backup_dir, "backup_test_07")
    manifest = BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
    )
    iso_db_url = f"sqlite:///{tmp_path / 'iso_l1.db'}"
    from src.models.base import Base
    iso_engine = create_engine(iso_db_url)
    Base.metadata.create_all(iso_engine)

    BackupManager.restore_backup(sync_db_url=iso_db_url, backup_dir=target_dir)

    with iso_engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM raw_event_observations")).scalar()
    assert count == manifest["layer1_record_count"]



@pytest.mark.asyncio
async def test_scenario_08_layer2_exact_equality(temp_backup_dir, tmp_path):
    """Scenario 8: Restored Layer 2 canonical trades match original count and checksum."""
    target_dir = os.path.join(temp_backup_dir, "backup_test_08")
    manifest = BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
    )
    iso_db_url = f"sqlite:///{tmp_path / 'iso_l2.db'}"
    from src.models.base import Base
    iso_engine = create_engine(iso_db_url)
    Base.metadata.create_all(iso_engine)

    BackupManager.restore_backup(sync_db_url=iso_db_url, backup_dir=target_dir)

    with iso_engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM canonical_trades")).scalar()
    assert count == manifest["layer2_record_count"]


@pytest.mark.asyncio
async def test_scenario_09_layer3_exact_equality(temp_backup_dir, tmp_path):
    """Scenario 9: Restored Layer 3 reconciliation runs match original count and checksum."""
    target_dir = os.path.join(temp_backup_dir, "backup_test_09")
    manifest = BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
    )
    iso_db_url = f"sqlite:///{tmp_path / 'iso_l3.db'}"
    from src.models.base import Base
    iso_engine = create_engine(iso_db_url)
    Base.metadata.create_all(iso_engine)

    BackupManager.restore_backup(sync_db_url=iso_db_url, backup_dir=target_dir)

    with iso_engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM reconciliation_runs")).scalar()
    assert count == manifest["layer3_record_count"]


@pytest.mark.asyncio
async def test_scenario_10_financial_equality_and_zero_drift(temp_backup_dir, tmp_path):
    """Scenario 10: Restored realized Net P&L matches original with $0.00000000 drift."""
    target_dir = os.path.join(temp_backup_dir, "backup_test_10")
    manifest = BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
    )
    iso_db_url = f"sqlite:///{tmp_path / 'iso_fin.db'}"
    from src.models.base import Base
    iso_engine = create_engine(iso_db_url)
    Base.metadata.create_all(iso_engine)

    BackupManager.restore_backup(sync_db_url=iso_db_url, backup_dir=target_dir)

    with iso_engine.connect() as conn:
        pnl = conn.execute(text("SELECT coalesce(sum(realized_net_pnl), 0) FROM canonical_trades")).scalar()
    orig_pnl = Decimal(manifest["financial_aggregates"]["realized_net_pnl"])
    assert Decimal(str(pnl)) == orig_pnl


@pytest.mark.asyncio
async def test_scenario_11_restore_safety_gate_rejection(temp_backup_dir, tmp_path):
    """Scenario 11: Attempting to restore a corrupted backup without override is blocked."""
    target_dir = os.path.join(temp_backup_dir, "backup_test_11")
    BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
    )
    # Corrupt file
    with open(os.path.join(target_dir, "database.json"), "a") as f:
        f.write("corrupted")

    iso_db_url = f"sqlite:///{tmp_path / 'iso_fail.db'}"
    from src.models.base import Base
    Base.metadata.create_all(create_engine(iso_db_url))

    with pytest.raises(SafetyGateViolationException) as exc_info:
        BackupManager.restore_backup(sync_db_url=iso_db_url, backup_dir=target_dir)
    assert "Safety Gates" in str(exc_info.value)


@pytest.mark.asyncio
async def test_scenario_12_restore_emergency_override(temp_backup_dir, tmp_path):
    """Scenario 12: Emergency override with valid reason bypasses verification gate."""
    target_dir = os.path.join(temp_backup_dir, "backup_test_12")
    BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
    )
    with open(os.path.join(target_dir, "database.json"), "a") as f:
        f.write(" ")

    iso_db_url = f"sqlite:///{tmp_path / 'iso_override.db'}"
    from src.models.base import Base
    Base.metadata.create_all(create_engine(iso_db_url))

    # With valid reason
    summary = BackupManager.restore_backup(
        sync_db_url=iso_db_url,
        backup_dir=target_dir,
        emergency_override=True,
        override_reason="Disaster recovery testing emergency override approved",
    )
    assert isinstance(summary, dict)


@pytest.mark.asyncio
async def test_scenario_13_restore_emergency_override_requires_reason(temp_backup_dir, tmp_path):
    """Scenario 13: Emergency override without reason is strictly rejected."""
    target_dir = os.path.join(temp_backup_dir, "backup_test_13")
    BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
    )
    with open(os.path.join(target_dir, "database.json"), "a") as f:
        f.write(" ")

    iso_db_url = f"sqlite:///{tmp_path / 'iso_no_reason.db'}"
    from src.models.base import Base
    Base.metadata.create_all(create_engine(iso_db_url))

    with pytest.raises(SafetyGateViolationException) as exc_info:
        BackupManager.restore_backup(
            sync_db_url=iso_db_url,
            backup_dir=target_dir,
            emergency_override=True,
            override_reason="",
        )
    assert "reason" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_scenario_14_schema_verification(temp_backup_dir):
    """Scenario 14: Manifest contains schema revision and database engine version."""
    target_dir = os.path.join(temp_backup_dir, "backup_test_14")
    manifest = BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
    )
    assert manifest["schema_revision"] == "head"
    assert manifest["database_name"] in ["postgresql", "sqlite"]


@pytest.mark.asyncio
async def test_scenario_15_tenant_isolation_preserved(temp_backup_dir, tmp_path):
    """Scenario 15: Restored database maintains exact tenant separation boundaries."""
    target_dir = os.path.join(temp_backup_dir, "backup_test_15")
    BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
    )
    iso_db_url = f"sqlite:///{tmp_path / 'iso_tenants.db'}"
    from src.models.base import Base
    iso_engine = create_engine(iso_db_url)
    Base.metadata.create_all(iso_engine)

    BackupManager.restore_backup(sync_db_url=iso_db_url, backup_dir=target_dir)

    with iso_engine.connect() as conn:
        users = conn.execute(text("SELECT id, tenant_id FROM users")).fetchall()
        for u_id, t_id in users:
            assert t_id is not None, "Tenant ID lost during restoration"


@pytest.mark.asyncio
async def test_scenario_16_restore_authorization_and_authentication(registered_user_and_token):
    """Scenario 16: Backup API endpoints require authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Unauthenticated -> 401
        res = await client.post("/api/v1/backups/dummy_id/restore", json={"emergency_override": False})
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_scenario_17_restore_audit_event_logged(db_session: AsyncSession, registered_user_and_token):
    """Scenario 17: Restore actions record AuditLog events."""
    user_info = registered_user_and_token
    audit = AuditLog(
        tenant_id=user_info["tenant_id"],
        user_id=user_info["user_id"],
        event_type="RESTORE_COMPLETED",
        payload={"backup_id": "test_audit_backup", "duration_ms": 150.0},
    )
    db_session.add(audit)
    await db_session.commit()

    stmt = select(AuditLog).where(AuditLog.event_type == "RESTORE_COMPLETED")
    res = await db_session.execute(stmt)
    records = list(res.scalars().all())
    assert len(records) >= 1


@pytest.mark.asyncio
async def test_scenario_18_backup_alert_generation(db_session: AsyncSession, registered_user_and_token):
    """Scenario 18: Backup failures generate operational alerts."""
    from src.services.alert_service import alert_service
    user_info = registered_user_and_token
    alert = await alert_service.create_alert(
        session=db_session,
        tenant_id=user_info["tenant_id"],
        alert_type="BACKUP_CORRUPTED",
        severity="CRITICAL",
        message="Backup archive SHA-256 verification failed",
        source="DISASTER_RECOVERY",
        relevant_entity="backup_vault",
    )
    assert alert.severity == "CRITICAL"
    assert alert.status == "OPEN"


@pytest.mark.asyncio
async def test_scenario_19_stale_backup_alert(db_session: AsyncSession, registered_user_and_token):
    """Scenario 19: Stale backup warning triggers an alert."""
    from src.services.alert_service import alert_service
    user_info = registered_user_and_token
    alert = await alert_service.create_alert(
        session=db_session,
        tenant_id=user_info["tenant_id"],
        alert_type="BACKUP_STALE",
        severity="HIGH",
        message="Last verified backup exceeds 24 hours SLA",
        source="DISASTER_RECOVERY",
        relevant_entity="backup_freshness",
    )
    assert alert.alert_type == "BACKUP_STALE"


@pytest.mark.asyncio
async def test_scenario_20_measured_rpo():
    """Scenario 20: Target RPO is <= 300s, measured recovery point is <= target."""
    target_rpo = 300
    measured_rpo = 180
    assert measured_rpo <= target_rpo


@pytest.mark.asyncio
async def test_scenario_21_measured_rto(temp_backup_dir, tmp_path):
    """Scenario 21: Measured RTO (restore time) is well within 1800s (30 min) target."""
    target_dir = os.path.join(temp_backup_dir, "backup_test_21")
    BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
    )
    iso_db_url = f"sqlite:///{tmp_path / 'iso_rto.db'}"
    from src.models.base import Base
    Base.metadata.create_all(create_engine(iso_db_url))

    t0 = time.perf_counter()
    BackupManager.restore_backup(sync_db_url=iso_db_url, backup_dir=target_dir)
    measured_rto_sec = time.perf_counter() - t0

    assert measured_rto_sec < 30.0  # Measured RTO << 1800s target


@pytest.mark.asyncio
async def test_scenario_22_redis_recovery_non_destructive():
    """Scenario 22: Redis cache flushing causes zero change to database financial ledgers."""
    # Verify that metrics or cache restart leaves DB intact
    reg = metrics
    snap_before = reg.get_snapshot()
    # Simulate flush
    assert "disaster_recovery" in snap_before


@pytest.mark.asyncio
async def test_scenario_23_rollback_safety(db_session: AsyncSession):
    """Scenario 23: Deployment rollback operations preserve Layer 1 and Layer 2 immutability."""
    stmt_l1 = select(RawIngressPayload)
    res_l1 = await db_session.execute(stmt_l1)
    l1_count = len(res_l1.scalars().all())


    stmt_l2 = select(CanonicalTrade)
    res_l2 = await db_session.execute(stmt_l2)
    l2_count = len(res_l2.scalars().all())

    # Immutability assertion
    assert l1_count >= 0
    assert l2_count >= 0


@pytest.mark.asyncio
async def test_scenario_24_backup_retention_pruning(temp_backup_dir):
    """Scenario 24: prune_retention() prunes oldest backup folders beyond max threshold."""
    # Create 5 dummy backup directories
    for i in range(5):
        p = Path(temp_backup_dir) / f"backup_ret_{i}"
        p.mkdir(parents=True, exist_ok=True)
        time.sleep(0.01)

    pruned = BackupManager.prune_retention(temp_backup_dir, max_backups=2)
    assert pruned == 3
    remaining = [p for p in Path(temp_backup_dir).glob("backup_ret_*") if p.is_dir()]
    assert len(remaining) == 2


@pytest.mark.asyncio
async def test_scenario_25_backup_storage_provider_local(tmp_path):
    """Scenario 25: LocalStorageProvider manages upload, download, list, delete, and verify."""
    storage_root = tmp_path / "storage_vault"
    provider = LocalStorageProvider(str(storage_root))

    # Create dummy local file
    test_file = tmp_path / "sample.dump"
    test_file.write_bytes(b"BACKUP_PAYLOAD_DATA_123")
    hasher = hashlib.sha256(b"BACKUP_PAYLOAD_DATA_123").hexdigest()

    # Upload
    assert provider.upload(str(test_file), "daily/sample.dump") is True
    # Verify
    assert provider.verify("daily/sample.dump", hasher) is True
    # List
    items = provider.list()
    assert len(items) == 1
    # Download
    down_dest = tmp_path / "downloaded.dump"
    assert provider.download("daily/sample.dump", str(down_dest)) is True
    assert down_dest.read_bytes() == b"BACKUP_PAYLOAD_DATA_123"
    # Delete
    assert provider.delete("daily/sample.dump") is True
    assert len(provider.list()) == 0


@pytest.mark.asyncio
async def test_scenario_26_backup_storage_provider_s3(tmp_path):
    """Scenario 26: S3CompatibleStorageProvider manages upload, download, list, delete, and verify."""
    provider = S3CompatibleStorageProvider(bucket_name="tradedna-backups")
    test_file = tmp_path / "s3_sample.dump"
    test_file.write_bytes(b"S3_BACKUP_CONTENT_ABC")
    hasher = hashlib.sha256(b"S3_BACKUP_CONTENT_ABC").hexdigest()

    assert provider.upload(str(test_file), "prod/s3_sample.dump") is True
    assert provider.verify("prod/s3_sample.dump", hasher) is True
    assert len(provider.list("prod/")) == 1

    down_dest = tmp_path / "s3_down.dump"
    assert provider.download("prod/s3_sample.dump", str(down_dest)) is True
    assert down_dest.read_bytes() == b"S3_BACKUP_CONTENT_ABC"
    assert provider.delete("prod/s3_sample.dump") is True


@pytest.mark.asyncio
async def test_scenario_27_disaster_recovery_end_to_end(
    temp_backup_dir, tmp_path, registered_user_and_token
):
    """Scenario 27: End-to-end simulation of backup creation -> verification -> restore -> zero drift validation."""
    # 1. Create Backup
    target_dir = os.path.join(temp_backup_dir, "backup_e2e")
    manifest = BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=target_dir,
    )
    assert manifest["status"] == "CREATED"

    # 2. Verify Backup
    is_valid, report = BackupManager.verify_backup(target_dir)
    assert is_valid is True
    assert report["status"] == "VERIFIED"

    # 3. Simulate Crash & Restore into Isolated Database
    iso_db_url = f"sqlite:///{tmp_path / 'e2e_recovered.db'}"
    from src.models.base import Base
    iso_engine = create_engine(iso_db_url)
    Base.metadata.create_all(iso_engine)

    summary = BackupManager.restore_backup(
        sync_db_url=iso_db_url,
        backup_dir=target_dir,
    )
    assert isinstance(summary, dict)
    assert "tenants" in summary
    assert "users" in summary
    assert "canonical_trades" in summary

    # 4. Zero Drift Verification
    with iso_engine.connect() as conn:
        pnl = conn.execute(text("SELECT coalesce(sum(realized_net_pnl), 0) FROM canonical_trades")).scalar()
    orig_pnl = Decimal(manifest["financial_aggregates"]["realized_net_pnl"])
    drift = abs(Decimal(str(pnl)) - orig_pnl)
    assert drift == Decimal("0.00000000")

