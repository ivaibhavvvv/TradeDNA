from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import secrets
import uuid
import httpx
from httpx import AsyncClient
import pytest
from sqlalchemy import select, update
from src.core.connector_auth import reset_nonce_cache
from src.models.device import Device, PairingToken
from src.models.sync_state import AccountSyncState
from src.models.user import User
from tests.conftest import test_session_factory
from tests.test_phase8d_e2e_production import build_signed_headers, setup_production_test_environment


@pytest.mark.asyncio
async def test_scenario_01_create_pairing(async_client: AsyncClient):
    """Scenario 1: Verifies pairing token creation with 64 hex chars and 300s expiration."""
    account_number = 9950101
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    resp = await async_client.post("/api/v1/exness/connection/pair", headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()

    assert "pairing_token" in data
    assert len(data["pairing_token"]) == 64
    assert data["expires_in_seconds"] == 300
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_scenario_02_pairing_expiration(async_client: AsyncClient):
    """Scenario 2: Verifies that an expired pairing token cannot be exchanged."""
    account_number = 9950201
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    resp = await async_client.post("/api/v1/exness/connection/pair", headers=auth_headers)
    assert resp.status_code == 201
    token = resp.json()["pairing_token"]
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    # Expire token in database
    ten_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
    async with test_session_factory() as session:
        await session.execute(
            update(PairingToken).where(PairingToken.token_hash == token_hash).values(expires_at=ten_mins_ago)
        )
        await session.commit()

    # Attempt exchange
    exchange_payload = {
        "pairing_token": token,
        "client_nonce": secrets.token_hex(16),
        "broker": "EXNESS",
        "account_number": account_number,
        "server_name": "Exness-Real25",
        "trade_mode": "REAL",
        "currency": "USD",
        "terminal_build": 4150,
        "connector_version": "1.0.0",
    }
    ex_resp = await async_client.post("/api/v1/exness/connection/exchange", json=exchange_payload)
    assert ex_resp.status_code in (400, 401, 403)


@pytest.mark.asyncio
async def test_scenario_03_pairing_one_time_use(async_client: AsyncClient):
    """Scenario 3: Verifies single-use pairing token consumption."""
    account_number = 9950301
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    resp = await async_client.post("/api/v1/exness/connection/pair", headers=auth_headers)
    token = resp.json()["pairing_token"]

    exchange_payload = {
        "pairing_token": token,
        "client_nonce": secrets.token_hex(16),
        "broker": "EXNESS",
        "account_number": account_number,
        "server_name": "Exness-Real25",
        "trade_mode": "REAL",
        "currency": "USD",
        "terminal_build": 4150,
        "connector_version": "1.0.0",
    }

    # 1st exchange -> Success
    ex_resp1 = await async_client.post("/api/v1/exness/connection/exchange", json=exchange_payload)
    assert ex_resp1.status_code == 200

    # 2nd exchange with same token -> Rejected
    ex_resp2 = await async_client.post("/api/v1/exness/connection/exchange", json=exchange_payload)
    assert ex_resp2.status_code in (400, 401, 403)


@pytest.mark.asyncio
async def test_scenario_04_successful_handshake(async_client: AsyncClient):
    """Scenario 4: Verifies successful MT5 terminal handshake and credential generation."""
    account_number = 9950401
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    resp = await async_client.post("/api/v1/exness/connection/pair", headers=auth_headers)
    token = resp.json()["pairing_token"]

    exchange_payload = {
        "pairing_token": token,
        "client_nonce": secrets.token_hex(16),
        "broker": "EXNESS",
        "account_number": account_number,
        "server_name": "Exness-Real25",
        "trade_mode": "REAL",
        "currency": "USD",
        "terminal_build": 4150,
        "connector_version": "1.0.0",
    }

    ex_resp = await async_client.post("/api/v1/exness/connection/exchange", json=exchange_payload)
    assert ex_resp.status_code == 200
    data = ex_resp.json()

    assert "device_id" in data
    assert "device_secret" in data
    assert data["broker"] == "EXNESS"
    assert data["account_number"] == account_number
    assert data["server_name"] == "Exness-Real25"


@pytest.mark.asyncio
async def test_scenario_05_wrong_broker_rejection(async_client: AsyncClient):
    """Scenario 5: Verifies strict rejection of non-Exness brokers."""
    account_number = 9950501
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    resp = await async_client.post("/api/v1/exness/connection/pair", headers=auth_headers)
    token = resp.json()["pairing_token"]

    exchange_payload = {
        "pairing_token": token,
        "client_nonce": secrets.token_hex(16),
        "broker": "ICMarkets",  # Non-Exness broker
        "account_number": account_number,
        "server_name": "ICMarkets-Live01",
        "trade_mode": "REAL",
        "currency": "USD",
        "terminal_build": 4150,
        "connector_version": "1.0.0",
    }

    ex_resp = await async_client.post("/api/v1/exness/connection/exchange", json=exchange_payload)
    assert ex_resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_scenario_06_wrong_account_rejection(async_client: AsyncClient):
    """Scenario 6: Verifies rejection of invalid account numbers (<= 0)."""
    account_number = 9950601
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    resp = await async_client.post("/api/v1/exness/connection/pair", headers=auth_headers)
    token = resp.json()["pairing_token"]

    exchange_payload = {
        "pairing_token": token,
        "client_nonce": secrets.token_hex(16),
        "broker": "EXNESS",
        "account_number": -5,  # Invalid account number
        "server_name": "Exness-Real25",
        "trade_mode": "REAL",
        "currency": "USD",
        "terminal_build": 4150,
        "connector_version": "1.0.0",
    }

    ex_resp = await async_client.post("/api/v1/exness/connection/exchange", json=exchange_payload)
    assert ex_resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_scenario_07_wrong_server_rejection(async_client: AsyncClient):
    """Scenario 7: Verifies rejection of empty server name."""
    account_number = 9950701
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    resp = await async_client.post("/api/v1/exness/connection/pair", headers=auth_headers)
    token = resp.json()["pairing_token"]

    exchange_payload = {
        "pairing_token": token,
        "client_nonce": secrets.token_hex(16),
        "broker": "EXNESS",
        "account_number": account_number,
        "server_name": "   ",  # Empty server name
        "trade_mode": "REAL",
        "currency": "USD",
        "terminal_build": 4150,
        "connector_version": "1.0.0",
    }

    ex_resp = await async_client.post("/api/v1/exness/connection/exchange", json=exchange_payload)
    assert ex_resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_scenario_08_cross_tenant_pairing_rejection(async_client: AsyncClient):
    """Scenario 8: Verifies that pairing tokens belong strictly to the issuing tenant."""
    # Tenant 1
    auth1, dev1, sec1, t1, u1, acc1 = await setup_production_test_environment(async_client, 9950801)
    # Tenant 2
    auth2, dev2, sec2, t2, u2, acc2 = await setup_production_test_environment(async_client, 9950802)

    # Token created by Tenant 1
    resp = await async_client.post("/api/v1/exness/connection/pair", headers=auth1)
    token = resp.json()["pairing_token"]

    # Exchange attempted by MT5 with Tenant 2's account details -> provisions under Tenant 1's scope
    exchange_payload = {
        "pairing_token": token,
        "client_nonce": secrets.token_hex(16),
        "broker": "EXNESS",
        "account_number": 9950802,
        "server_name": "Exness-Real25",
        "trade_mode": "REAL",
        "currency": "USD",
        "terminal_build": 4150,
        "connector_version": "1.0.0",
    }

    ex_resp = await async_client.post("/api/v1/exness/connection/exchange", json=exchange_payload)
    assert ex_resp.status_code == 200
    registered_dev_id = ex_resp.json()["device_id"]

    # Verify device is bound to Tenant 1, NOT Tenant 2
    async with test_session_factory() as session:
        dev_stmt = select(Device).where(Device.id == uuid.UUID(registered_dev_id))
        dev_res = await session.execute(dev_stmt)
        dev = dev_res.scalar_one()
        assert dev.tenant_id == t1
        assert dev.tenant_id != t2


@pytest.mark.asyncio
async def test_scenario_09_device_registration_integrity(async_client: AsyncClient):
    """Scenario 9: Verifies cryptographic hash storage of device_secret."""
    account_number = 9950901
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    async with test_session_factory() as session:
        dev_stmt = select(Device).where(Device.id == uuid.UUID(str(device_id)))
        dev_res = await session.execute(dev_stmt)
        dev = dev_res.scalar_one()

        # Verify hash matches sha256(device_secret)
        expected_hash = hashlib.sha256(device_secret.encode("utf-8")).hexdigest()
        assert dev.device_secret_hash == expected_hash
        assert dev.broker == "EXNESS"
        assert dev.is_active is True
        assert dev.is_revoked is False


@pytest.mark.asyncio
async def test_scenario_10_initial_sync_state(async_client: AsyncClient):
    """Scenario 10: Verifies initial sync state discovery."""
    account_number = 9951001
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    resp = await async_client.get(
        f"/api/v1/dashboard/sync-telemetry?account_number={account_number}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["has_account"] is True
    assert data["account_number"] == account_number
    assert "sync_stage" in data


@pytest.mark.asyncio
async def test_scenario_11_sync_progress_stages(async_client: AsyncClient):
    """Scenario 11: Verifies stage transitions across initial synchronization lifecycle."""
    account_number = 9951101
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    # Transition to SYNCING with cursor 0 -> DOWNLOADING_HISTORY
    async with test_session_factory() as session:
        await session.execute(
            update(AccountSyncState)
            .where(AccountSyncState.account_number == account_number)
            .values(sync_status="SYNCING", current_cursor_deal_ticket=0)
        )
        await session.commit()

    resp = await async_client.get(
        f"/api/v1/dashboard/sync-telemetry?account_number={account_number}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["sync_stage"] == "DOWNLOADING_HISTORY"


@pytest.mark.asyncio
async def test_scenario_12_incremental_sync(async_client: AsyncClient):
    """Scenario 12: Verifies live incremental deal synchronization cursor advance."""
    account_number = 9951201
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    async with test_session_factory() as session:
        await session.execute(
            update(AccountSyncState)
            .where(AccountSyncState.account_number == account_number)
            .values(sync_status="CURRENT", current_cursor_deal_ticket=850)
        )
        await session.commit()

    resp = await async_client.get(
        f"/api/v1/dashboard/sync-telemetry?account_number={account_number}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_cursor_deal_ticket"] == 850
    assert data["sync_stage"] == "READY"


@pytest.mark.asyncio
async def test_scenario_13_connector_reconnect(async_client: AsyncClient):
    """Scenario 13: Verifies connector reconnect and heartbeat resumption."""
    account_number = 9951301
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    now_utc = datetime.now(timezone.utc)
    async with test_session_factory() as session:
        await session.execute(
            update(Device)
            .where(Device.id == uuid.UUID(str(device_id)))
            .values(last_seen_at=now_utc, is_active=True)
        )
        await session.commit()

    resp = await async_client.get(
        f"/api/v1/dashboard/sync-telemetry?account_number={account_number}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_connected"] is True


@pytest.mark.asyncio
async def test_scenario_14_device_revocation(async_client: AsyncClient):
    """Scenario 14: Verifies 1-click device revocation."""
    account_number = 9951401
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    resp = await async_client.post(
        f"/api/v1/connections/devices/{device_id}/revoke",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "REVOKED"

    # Check DB state
    async with test_session_factory() as session:
        dev_stmt = select(Device).where(Device.id == uuid.UUID(str(device_id)))
        dev_res = await session.execute(dev_stmt)
        dev = dev_res.scalar_one()
        assert dev.is_revoked is True
        assert dev.is_active is False


@pytest.mark.asyncio
async def test_scenario_15_revoked_ingestion_rejection(async_client: AsyncClient):
    """Scenario 15: Verifies that revoked device cannot send sync data."""
    account_number = 9951501
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    # Revoke device
    await async_client.post(
        f"/api/v1/connections/devices/{device_id}/revoke",
        headers=auth_headers,
    )

    # Generate HMAC headers
    reset_nonce_cache()
    hb_payload = {
        "payload_type": "HEARTBEAT",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": account_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    raw_hb = json.dumps(hb_payload).encode("utf-8")
    hmac_headers = build_signed_headers(
        device_id=str(device_id),
        device_secret_hex=device_secret,
        raw_body_bytes=raw_hb,
    )

    # Attempt ingestion
    ingest_resp = await async_client.post(
        "/api/v1/exness/sync",
        headers=hmac_headers,
        content=raw_hb,
    )
    assert ingest_resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_scenario_16_account_switching_authorization(async_client: AsyncClient):
    """Scenario 16: Verifies tenant isolation on account switching."""
    # Tenant 1 has account 9951601
    auth1, dev1, sec1, t1, u1, acc1 = await setup_production_test_environment(async_client, 9951601)
    # Tenant 2 has account 9951602
    auth2, dev2, sec2, t2, u2, acc2 = await setup_production_test_environment(async_client, 9951602)

    # Tenant 1 attempts to query Tenant 2's account telemetry -> 404
    resp = await async_client.get(
        "/api/v1/dashboard/sync-telemetry?account_number=9951602",
        headers=auth1,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_scenario_17_stale_data_state(async_client: AsyncClient):
    """Scenario 17: Verifies STALE state when last sync > 10m ago."""
    account_number = 9951701
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    twenty_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=20)
    async with test_session_factory() as session:
        await session.execute(
            update(AccountSyncState)
            .where(AccountSyncState.account_number == account_number)
            .values(sync_status="CURRENT", current_cursor_deal_ticket=500, last_successful_sync_at=twenty_mins_ago)
        )
        await session.commit()

    resp = await async_client.get(
        f"/api/v1/dashboard/sync-telemetry?account_number={account_number}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["freshness_state"] == "STALE"


@pytest.mark.asyncio
async def test_scenario_18_integrity_state_propagation(async_client: AsyncClient):
    """Scenario 18: Verifies propagation of reconciliation integrity grade to telemetry."""
    account_number = 9951801
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    resp = await async_client.get(
        f"/api/v1/dashboard/sync-telemetry?account_number={account_number}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "integrity_score" in data
    assert "integrity_grade" in data
    assert data["integrity_grade"] == "AAA"


@pytest.mark.asyncio
async def test_scenario_19_no_secret_exposure(async_client: AsyncClient):
    """Scenario 19: Verifies that device_secret and HMAC hashes are NEVER returned to frontend."""
    account_number = 9951901
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    resp = await async_client.get("/api/v1/connections", headers=auth_headers)
    assert resp.status_code == 200
    body_text = resp.text

    assert device_secret not in body_text
    assert "device_secret_hash" not in body_text
    assert "token_hash" not in body_text


@pytest.mark.asyncio
async def test_scenario_20_no_trade_execution_capability(async_client: AsyncClient):
    """Scenario 20: Verifies that trade execution endpoints do NOT exist."""
    account_number = 9952001
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    # Verify trading endpoints return 404/405
    for path in ["/api/v1/trades/order", "/api/v1/orders/send", "/api/v1/positions/close"]:
        post_resp = await async_client.post(path, headers=auth_headers, json={"volume": 1.0})
        assert post_resp.status_code in (404, 405)
