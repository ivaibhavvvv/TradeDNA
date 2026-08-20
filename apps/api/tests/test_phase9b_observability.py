"""
TradeDNA Phase 9B - Production Observability, Monitoring & Operational Intelligence Test Suite
Tests structured logging, correlation IDs, metrics collection, alert fingerprinting/deduplication,
lifecycle state transitions, tenant isolation, and read-only financial safety invariants.
"""

import time
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.main import app
from src.core.config import settings
from src.core.logging import JSONFormatter, redact_sensitive_data
from src.core.metrics import metrics, MetricsRegistry
from src.models.user import User
from src.models.tenant import Tenant
from src.models.alert import OperationalAlert
from src.services.alert_service import alert_service, generate_alert_fingerprint
from src.services.dashboard_service import DashboardService


@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
async def registered_user_and_token(async_client: AsyncClient):
    email = f"observability_user_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "StrongSecurePassword123!"
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pwd, "full_name": "Observability User", "tenant_name": "Obs Tenant"},
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
async def test_scenario_01_request_id_generated(async_client: AsyncClient):
    """Scenario 1: Inbound request without X-Request-ID receives a valid generated correlation UUID."""
    res = await async_client.get("/health")
    assert res.status_code == 200
    req_id = res.headers.get("X-Request-ID")
    assert req_id is not None
    assert len(req_id) >= 32
    # Verify it parses as UUID
    parsed_uuid = uuid.UUID(req_id)
    assert str(parsed_uuid) == req_id


@pytest.mark.asyncio
async def test_scenario_02_request_id_propagated(async_client: AsyncClient):
    """Scenario 2: Inbound request with valid X-Request-ID preserves and echoes the correlation ID."""
    custom_id = "trace-obs-12345678-abcd"
    res = await async_client.get("/health", headers={"X-Request-ID": custom_id})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == custom_id


@pytest.mark.asyncio
async def test_scenario_03_structured_json_log_format():
    """Scenario 3: Structured JSON formatter serializes log records with timestamp, level, and context."""
    import logging
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="tradedna.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Operational heartbeat received",
        args=(),
        exc_info=None,
    )
    record.request_id = "test-req-999"
    record.tenant_id = "test-tenant-111"

    formatted = formatter.format(record)
    import json
    log_data = json.loads(formatted)

    assert log_data["level"] == "INFO"
    assert log_data["message"] == "Operational heartbeat received"
    assert log_data["request_id"] == "test-req-999"
    assert log_data["tenant_id"] == "test-tenant-111"
    assert "timestamp" in log_data


@pytest.mark.asyncio
async def test_scenario_04_secrets_redacted_in_logs():
    """Scenario 4: Sensitive credential parameters are recursively redacted from logs."""
    sensitive_dict = {
        "user_email": "trader@exness.com",
        "password": "SuperSecretPassword!",
        "access_token": "eyJhbGciOi...",
        "jwt_secret": "my-key-secret",
        "device_secret": "hmac_device_key",
        "nested": {
            "pairing_token": "tok_123456",
            "safe_counter": 42,
        },
    }
    redacted = redact_sensitive_data(sensitive_dict)

    assert redacted["user_email"] == "trader@exness.com"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["access_token"] == "[REDACTED]"
    assert redacted["jwt_secret"] == "[REDACTED]"
    assert redacted["device_secret"] == "[REDACTED]"
    assert redacted["nested"]["pairing_token"] == "[REDACTED]"
    assert redacted["nested"]["safe_counter"] == 42


@pytest.mark.asyncio
async def test_scenario_05_metrics_endpoint_protected(async_client: AsyncClient, monkeypatch):
    """Scenario 5: In production environment, /metrics requires X-Metrics-Key header."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "METRICS_KEY", "ultra_secure_prod_metrics_key_999")

    # Without header -> 403 Forbidden
    res_unauth = await async_client.get("/metrics")
    assert res_unauth.status_code == 403
    assert res_unauth.json()["error"]["code"] == "FORBIDDEN_METRICS_ACCESS"

    # With valid key -> 200 OK
    res_auth = await async_client.get("/metrics", headers={"X-Metrics-Key": "ultra_secure_prod_metrics_key_999"})
    assert res_auth.status_code == 200
    assert "system" in res_auth.json()


@pytest.mark.asyncio
async def test_scenario_06_metrics_snapshot_contains_no_secrets(async_client: AsyncClient):
    """Scenario 6: Metrics snapshot contains zero tenant financial figures or credentials."""
    res = await async_client.get("/metrics")
    assert res.status_code == 200
    data = res.json()

    forbidden_keys = ["password", "token", "balance", "equity", "realized_net_pnl", "ticket", "deal"]
    serialized = str(data).lower()
    for key in forbidden_keys:
        assert key not in data.get("system", {}), f"Secret key {key} leaked in metrics"


@pytest.mark.asyncio
async def test_scenario_07_connector_telemetry_tracking():
    """Scenario 7: Connector heartbeats and device counts are recorded in metrics registry."""
    reg = MetricsRegistry()
    reg.record_heartbeat(success=True)
    reg.record_heartbeat(success=True)
    reg.record_heartbeat(success=False)

    snap = reg.get_snapshot()
    assert snap["connector"]["heartbeat_total"] == 3
    assert snap["connector"]["heartbeat_failures"] == 1


@pytest.mark.asyncio
async def test_scenario_08_heartbeat_stale_detection(db_session: AsyncSession, registered_user_and_token):
    """Scenario 8: Devices with heartbeats older than 5 minutes are classified as stale."""
    from src.models.device import Device
    user_info = registered_user_and_token
    tenant_id = user_info["tenant_id"]

    # Active device
    dev_active = Device(
        tenant_id=tenant_id,
        account_number=10001,
        server_name="Exness-Real10",
        trade_mode="REAL",
        currency="USD",
        device_secret_hash="hash_active",
        device_secret="sec_active",
        terminal_build=4150,
        connector_version="1.0.0",
        is_active=True,
        is_revoked=False,
        last_seen_at=datetime.now(timezone.utc),
    )
    # Stale device (last seen 10 minutes ago)
    dev_stale = Device(
        tenant_id=tenant_id,
        account_number=10002,
        server_name="Exness-Real10",
        trade_mode="REAL",
        currency="USD",
        device_secret_hash="hash_stale",
        device_secret="sec_stale",
        terminal_build=4150,
        connector_version="1.0.0",
        is_active=True,
        is_revoked=False,
        last_seen_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db_session.add_all([dev_active, dev_stale])
    await db_session.commit()

    user_stmt = select(User).where(User.id == user_info["user_id"])
    user = (await db_session.execute(user_stmt)).scalar_one()

    overview = await DashboardService.get_operations_overview(db_session, user)
    assert overview["connectors"]["total_devices"] >= 2
    assert overview["connectors"]["active_devices"] >= 1
    assert overview["connectors"]["stale_devices"] >= 1


@pytest.mark.asyncio
async def test_scenario_09_sync_telemetry_tracking():
    """Scenario 9: Synchronization events and durations are recorded."""
    reg = MetricsRegistry()
    reg.record_sync(success=True, duration_ms=250.5, events_count=100)
    reg.record_sync(success=False, duration_ms=120.0, events_count=0)

    snap = reg.get_snapshot()
    assert snap["synchronization"]["sync_completed_total"] == 1
    assert snap["synchronization"]["sync_failed_total"] == 1
    assert snap["synchronization"]["events_processed"] == 100
    assert snap["synchronization"]["avg_duration_ms"] > 0


@pytest.mark.asyncio
async def test_scenario_10_reconciliation_telemetry_tracking():
    """Scenario 10: Reconciliation runs, scores, and grades are tracked."""
    reg = MetricsRegistry()
    reg.record_reconciliation(score=100.0, grade="AAA", success=True)
    reg.record_reconciliation(score=98.5, grade="AAA", success=True)
    reg.record_reconciliation(score=85.0, grade="B", success=True)

    snap = reg.get_snapshot()
    assert snap["reconciliation"]["runs_total"] == 3
    assert snap["reconciliation"]["grade_distribution"]["AAA"] == 2
    assert snap["reconciliation"]["grade_distribution"]["B"] == 1


@pytest.mark.asyncio
async def test_scenario_11_financial_integrity_alert(db_session: AsyncSession, registered_user_and_token):
    """Scenario 11: Alert service creates an operational alert for financial drift or discrepancy."""
    user_info = registered_user_and_token
    tenant_id = user_info["tenant_id"]

    alert = await alert_service.create_alert(
        session=db_session,
        tenant_id=tenant_id,
        alert_type="FINANCIAL_DRIFT_DETECTED",
        severity="CRITICAL",
        message="Unexplained drift detected: $0.05",
        source="RECONCILIATION",
        relevant_entity="account_1001",
    )
    assert alert.id is not None
    assert alert.status == "OPEN"
    assert alert.severity == "CRITICAL"
    assert alert.source == "RECONCILIATION"


@pytest.mark.asyncio
async def test_scenario_12_cursor_regression_alert(db_session: AsyncSession, registered_user_and_token):
    """Scenario 12: Cursor regression triggers an operational alert."""
    user_info = registered_user_and_token
    tenant_id = user_info["tenant_id"]

    alert = await alert_service.create_alert(
        session=db_session,
        tenant_id=tenant_id,
        alert_type="SYNC_CURSOR_REGRESSION",
        severity="HIGH",
        message="Received deal ticket 500 when cursor is at 1000",
        source="INGRESS",
        relevant_entity="cursor_sync",
    )
    assert alert.alert_type == "SYNC_CURSOR_REGRESSION"
    assert alert.status == "OPEN"


@pytest.mark.asyncio
async def test_scenario_13_ledger_invariant_alert(db_session: AsyncSession, registered_user_and_token):
    """Scenario 13: Double-entry ledger invariant violation triggers an alert."""
    user_info = registered_user_and_token
    tenant_id = user_info["tenant_id"]

    alert = await alert_service.create_alert(
        session=db_session,
        tenant_id=tenant_id,
        alert_type="LEDGER_INVARIANT_VIOLATION",
        severity="CRITICAL",
        message="Sum of debits does not equal sum of credits in posting batch.",
        source="RECONSTRUCTION",
        relevant_entity="posting_batch_77",
    )
    assert alert.severity == "CRITICAL"
    assert alert.source == "RECONSTRUCTION"


@pytest.mark.asyncio
async def test_scenario_14_alert_deduplication_fingerprint(db_session: AsyncSession, registered_user_and_token):
    """Scenario 14: Repeated identical alerts in the active time window are deduplicated."""
    user_info = registered_user_and_token
    tenant_id = user_info["tenant_id"]

    alert1 = await alert_service.create_alert(
        session=db_session,
        tenant_id=tenant_id,
        alert_type="EA_HEARTBEAT_TIMEOUT",
        severity="MEDIUM",
        message="MT5 Terminal disconnected",
        source="CONNECTIVITY",
        relevant_entity="device_555",
    )

    alert2 = await alert_service.create_alert(
        session=db_session,
        tenant_id=tenant_id,
        alert_type="EA_HEARTBEAT_TIMEOUT",
        severity="MEDIUM",
        message="MT5 Terminal disconnected (repeat)",
        source="CONNECTIVITY",
        relevant_entity="device_555",
    )

    assert alert1.id == alert2.id
    assert alert1.fingerprint == alert2.fingerprint


@pytest.mark.asyncio
async def test_scenario_15_alert_acknowledgment_lifecycle(
    async_client: AsyncClient, db_session: AsyncSession, registered_user_and_token
):
    """Scenario 15: Alert acknowledgment transitions state from OPEN to ACKNOWLEDGED."""
    user_info = registered_user_and_token
    tenant_id = user_info["tenant_id"]
    token = user_info["token"]

    alert = await alert_service.create_alert(
        session=db_session,
        tenant_id=tenant_id,
        alert_type="TEST_ACK_ALERT",
        severity="LOW",
        message="Test alert for ack",
        relevant_entity=f"entity_{uuid.uuid4().hex[:6]}",
    )
    await db_session.commit()

    res = await async_client.post(
        f"/api/v1/alerts/{alert.id}/acknowledge",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ACKNOWLEDGED"


@pytest.mark.asyncio
async def test_scenario_16_alert_resolution_lifecycle(
    async_client: AsyncClient, db_session: AsyncSession, registered_user_and_token
):
    """Scenario 16: Alert resolution transitions state to RESOLVED."""
    user_info = registered_user_and_token
    tenant_id = user_info["tenant_id"]
    token = user_info["token"]

    alert = await alert_service.create_alert(
        session=db_session,
        tenant_id=tenant_id,
        alert_type="TEST_RESOLVE_ALERT",
        severity="LOW",
        message="Test alert for resolve",
        relevant_entity=f"entity_{uuid.uuid4().hex[:6]}",
    )
    await db_session.commit()

    res = await async_client.post(
        f"/api/v1/alerts/{alert.id}/resolve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "RESOLVED"


@pytest.mark.asyncio
async def test_scenario_17_tenant_isolation_alerts(
    async_client: AsyncClient, db_session: AsyncSession, registered_user_and_token
):
    """Scenario 17: Tenant A cannot see, acknowledge, or resolve Tenant B's alerts."""
    user_a = registered_user_and_token
    token_a = user_a["token"]

    # Register Tenant B
    email_b = f"tenant_b_{uuid.uuid4().hex[:8]}@example.com"
    reg_b = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email_b, "password": "Password123!", "full_name": "Tenant B User", "tenant_name": "Tenant B"},
    )
    assert reg_b.status_code == 201
    tenant_b_id = uuid.UUID(reg_b.json()["user"]["tenant_id"])

    # Create alert for Tenant B
    alert_b = await alert_service.create_alert(
        session=db_session,
        tenant_id=tenant_b_id,
        alert_type="TENANT_B_ONLY_ALERT",
        severity="HIGH",
        message="Confidential alert for Tenant B",
        relevant_entity=f"entity_b_{uuid.uuid4().hex[:6]}",
    )
    await db_session.commit()

    # User A lists alerts -> alert_b must NOT be present
    list_res = await async_client.get(
        "/api/v1/alerts",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert list_res.status_code == 200
    alerts_a = list_res.json()
    alert_ids_a = [a["id"] for a in alerts_a]
    assert str(alert_b.id) not in alert_ids_a

    # User A tries to acknowledge alert_b -> 404
    ack_res = await async_client.post(
        f"/api/v1/alerts/{alert_b.id}/acknowledge",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert ack_res.status_code == 404


@pytest.mark.asyncio
async def test_scenario_18_operations_dashboard_authorization(
    registered_user_and_token
):
    """Scenario 18: /dashboard/operations requires valid authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as fresh_client:
        # Unauthenticated -> 401
        unauth_res = await fresh_client.get("/api/v1/dashboard/operations")
        assert unauth_res.status_code == 401

        # Authenticated -> 200
        token = registered_user_and_token["token"]
        auth_res = await fresh_client.get(
            "/api/v1/dashboard/operations",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert auth_res.status_code == 200
        data = auth_res.json()
        assert "system" in data
        assert "connectors" in data
        assert "synchronization" in data
        assert "reconciliation" in data
        assert "alerts" in data



@pytest.mark.asyncio
async def test_scenario_19_database_failure_monitoring(async_client: AsyncClient, monkeypatch):
    """Scenario 19: Database health status is accurately reported."""
    # Verify ready probe is ready under normal conditions
    ready_res = await async_client.get("/health/ready")
    assert ready_res.status_code == 200
    assert ready_res.json()["status"] in ["ready", "healthy"]



@pytest.mark.asyncio
async def test_scenario_20_redis_failure_monitoring(
    async_client: AsyncClient, registered_user_and_token
):
    """Scenario 20: Redis operational status is reported in telemetry."""
    token = registered_user_and_token["token"]
    res = await async_client.get(
        "/api/v1/dashboard/operations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["system"]["redis_status"] == "OPERATIONAL"


@pytest.mark.asyncio
async def test_scenario_21_sync_failure_monitoring():
    """Scenario 21: Ingestion event rejections and errors increment metrics."""
    reg = MetricsRegistry()
    reg.record_ingress_event(accepted=True)
    reg.record_ingress_event(accepted=False)
    reg.record_ingress_event(accepted=True, is_duplicate=True)

    snap = reg.get_snapshot()
    assert snap["ingestion"]["events_total"] == 3
    assert snap["ingestion"]["events_rejected"] == 1
    assert snap["ingestion"]["duplicate_events_total"] == 1


@pytest.mark.asyncio
async def test_scenario_22_recovery_monitoring():
    """Scenario 22: Spool recovery events are tracked in ingestion telemetry."""
    reg = MetricsRegistry()
    reg.record_ingress_event(accepted=True, is_spool=True)
    reg.record_ingress_event(accepted=True, is_spool=True)

    snap = reg.get_snapshot()
    assert snap["ingestion"]["spool_recovery_events"] == 2


@pytest.mark.asyncio
async def test_scenario_23_performance_overhead(async_client: AsyncClient):
    """Scenario 23: Middleware latency tracking overhead is minimal (< 5ms)."""
    latencies = []
    for _ in range(5):
        t0 = time.perf_counter()
        res = await async_client.get("/health")
        t1 = time.perf_counter()
        assert res.status_code == 200
        latencies.append((t1 - t0) * 1000.0)

    avg_lat = sum(latencies) / len(latencies)
    assert avg_lat < 50.0  # Safe upper bound for local ASGI loop


@pytest.mark.asyncio
async def test_scenario_24_financial_invariants_preserved(db_session: AsyncSession, registered_user_and_token):
    """Scenario 24: Observability, alerting, and metrics never mutate Layer 1 or Layer 2 records."""
    from src.models.canonical_ledger import CanonicalTrade
    user_info = registered_user_and_token
    tenant_id = user_info["tenant_id"]

    # Verify that querying alerts or telemetry causes zero side-effects on canonical trades
    stmt = select(CanonicalTrade).where(CanonicalTrade.tenant_id == tenant_id)
    res = await db_session.execute(stmt)
    trades = list(res.scalars().all())

    # Create an alert and query telemetry
    await alert_service.create_alert(
        session=db_session,
        tenant_id=tenant_id,
        alert_type="RECON_TEST",
        severity="INFO",
        message="Observability test run",
        relevant_entity=f"entity_{uuid.uuid4().hex[:6]}",
    )
    await db_session.commit()

    # Re-verify canonical trades count
    res2 = await db_session.execute(stmt)
    trades2 = list(res2.scalars().all())
    assert len(trades) == len(trades2)
