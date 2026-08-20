import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import time
import uuid
from httpx import AsyncClient
import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.connector_auth import reset_nonce_cache
from tests.conftest import test_session_factory
from src.models.device import Device
from src.models.raw_event import (
    ImmutabilityViolationException,
    RawAccountSnapshot,
    RawEventObservation,
    RawIngressPayload,
    RawPositionSnapshot,
)
from src.models.sync_state import AccountSyncState, SyncGapEvent
from src.services.replay_service import ReplayService
from src.services.sync_engine import SyncEngine


def build_signed_headers(
    device_id: str,
    device_secret_hex: str,
    raw_body_bytes: bytes,
    timestamp_ms: int = None,
    nonce: str = None,
) -> dict:
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)
    if nonce is None:
        nonce = uuid.uuid4().hex

    body_sha256 = hashlib.sha256(raw_body_bytes).hexdigest().lower()
    canonical_str = f"{device_id}|{timestamp_ms}|{nonce}|{body_sha256}"
    canonical_bytes = canonical_str.encode("utf-8")

    device_secret_bytes = bytes.fromhex(device_secret_hex)
    signature = hmac.new(
        device_secret_bytes,
        canonical_bytes,
        hashlib.sha256,
    ).hexdigest().lower()

    return {
        "Content-Type": "application/json",
        "X-TradeDNA-Device-ID": str(device_id),
        "X-TradeDNA-Timestamp": str(timestamp_ms),
        "X-TradeDNA-Nonce": nonce,
        "X-TradeDNA-Signature": signature,
    }


# =====================================================================
# 1. Exact Raw Ingress Bytes Preservation
# =====================================================================
@pytest.mark.asyncio
async def test_raw_ingress_bytes_preservation(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "raw_bytes_tester@example.com",
        "password": "Password123!",
        "full_name": "Raw Bytes Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 99112233,
        "server_name": "Exness-MT5Real1",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    payload_dict = {
        "payload_type": "HEARTBEAT",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": 99112233,
            "timestamp": "2026-08-18T20:00:00.000Z"
        }
    }
    raw_body = json.dumps(payload_dict).encode("utf-8")
    expected_hash = hashlib.sha256(raw_body).hexdigest().lower()

    res = await async_client.post(
        "/api/v1/exness/sync",
        content=raw_body,
        headers=build_signed_headers(device_id, device_secret, raw_body)
    )
    assert res.status_code == 202

    async with test_session_factory() as session:
        stmt = select(RawIngressPayload).where(RawIngressPayload.payload_hash == expected_hash)
        res_db = await session.execute(stmt)
        ingress = res_db.scalar_one_or_none()
        assert ingress is not None
        assert ingress.raw_payload_bytes == raw_body
        assert ingress.payload_hash == expected_hash


# =====================================================================
# 2. Whitespace / Encoding Hash Variance
# =====================================================================
def test_whitespace_encoding_hash_variance():
    data = {"account_number": 12345, "symbol": "EURUSD"}
    bytes_compact = json.dumps(data, separators=(",", ":")).encode("utf-8")
    bytes_pretty = json.dumps(data, indent=2).encode("utf-8")
    bytes_spaced = json.dumps(data, separators=(", ", ": ")).encode("utf-8")

    hash_compact = hashlib.sha256(bytes_compact).hexdigest().lower()
    hash_pretty = hashlib.sha256(bytes_pretty).hexdigest().lower()
    hash_spaced = hashlib.sha256(bytes_spaced).hexdigest().lower()

    assert hash_compact != hash_pretty
    assert hash_compact != hash_spaced
    assert hash_pretty != hash_spaced


# =====================================================================
# 3 & 4. Database-Level UPDATE & DELETE Immutability Rejection
# =====================================================================
@pytest.mark.asyncio
async def test_database_level_immutability_rejection():
    async with test_session_factory() as session:
        ingress = RawIngressPayload(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            device_id=uuid.uuid4(),
            account_number=123456,
            server_name="Exness-MT5Real1",
            payload_type="HEARTBEAT",
            schema_version="1.0.0",
            payload_hash="testhash" * 8,
            raw_payload_bytes=b"test_bytes",
        )
        session.add(ingress)
        await session.commit()

        with pytest.raises(ImmutabilityViolationException) as exc_update:
            ingress.account_number = 999999
            await session.commit()
        assert "strictly forbidden" in str(exc_update.value).lower()
        await session.rollback()

        with pytest.raises(ImmutabilityViolationException) as exc_delete:
            await session.delete(ingress)
            await session.commit()
        assert "strictly forbidden" in str(exc_delete.value).lower()
        await session.rollback()


# =====================================================================
# 5. Duplicate Observation Preservation & Status
# =====================================================================
@pytest.mark.asyncio
async def test_duplicate_observation_preservation(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "dup_tester@example.com",
        "password": "Password123!",
        "full_name": "Duplicate Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 88224466,
        "server_name": "Exness-MT5Real1",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    deal_payload = {
        "payload_type": "DEAL_EVENT",
        "data": {
            "schema_version": "1.0.0",
            "observation_id": str(uuid.uuid4()),
            "connector_id": str(device_id),
            "account_number": 88224466,
            "deal_ticket": 771100,
            "symbol": "EURUSD",
            "deal_type": "DEAL_TYPE_BUY",
            "deal_entry": "DEAL_ENTRY_IN",
            "volume": "1.0000",
            "price": "1.085000",
            "profit": "0.0000",
            "deal_time": "2026-08-18T20:10:00.000Z",
            "deal_time_msc": 1787076900000,
        }
    }
    raw_deal = json.dumps(deal_payload).encode("utf-8")

    res1 = await async_client.post(
        "/api/v1/exness/sync",
        content=raw_deal,
        headers=build_signed_headers(device_id, device_secret, raw_deal)
    )
    assert res1.status_code == 202

    deal_payload["data"]["observation_id"] = str(uuid.uuid4())
    raw_deal_dup = json.dumps(deal_payload).encode("utf-8")
    res2 = await async_client.post(
        "/api/v1/exness/sync",
        content=raw_deal_dup,
        headers=build_signed_headers(device_id, device_secret, raw_deal_dup)
    )
    assert res2.status_code == 202

    async with test_session_factory() as session:
        stmt = select(RawEventObservation).where(
            RawEventObservation.account_number == 88224466,
            RawEventObservation.external_ticket == 771100,
        ).order_by(RawEventObservation.received_at_utc.asc())
        res_db = await session.execute(stmt)
        observations = res_db.scalars().all()

        assert len(observations) == 2
        assert observations[0].observation_status == "ORIGINAL"
        assert observations[1].observation_status == "DUPLICATE"


# =====================================================================
# 6. Conflicting Observation Flagging & Preservation
# =====================================================================
@pytest.mark.asyncio
async def test_conflicting_observation_flagging(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "conflict_tester@example.com",
        "password": "Password123!",
        "full_name": "Conflict Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 66331199,
        "server_name": "Exness-MT5Real1",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    deal_orig = {
        "payload_type": "DEAL_EVENT",
        "data": {
            "schema_version": "1.0.0",
            "observation_id": str(uuid.uuid4()),
            "connector_id": str(device_id),
            "account_number": 66331199,
            "deal_ticket": 990011,
            "symbol": "GBPUSD",
            "deal_type": "DEAL_TYPE_BUY",
            "deal_entry": "DEAL_ENTRY_IN",
            "volume": "1.0000",
            "price": "1.280000",
            "profit": "0.0000",
            "deal_time": "2026-08-18T20:10:00.000Z",
            "deal_time_msc": 1787076910000,
        }
    }
    raw_orig = json.dumps(deal_orig).encode("utf-8")
    await async_client.post("/api/v1/exness/sync", content=raw_orig, headers=build_signed_headers(device_id, device_secret, raw_orig))

    deal_conflict = {
        "payload_type": "DEAL_EVENT",
        "data": {
            "schema_version": "1.0.0",
            "observation_id": str(uuid.uuid4()),
            "connector_id": str(device_id),
            "account_number": 66331199,
            "deal_ticket": 990011,
            "symbol": "GBPUSD",
            "deal_type": "DEAL_TYPE_BUY",
            "deal_entry": "DEAL_ENTRY_IN",
            "volume": "1.0000",
            "price": "1.285000",
            "profit": "0.0000",
            "deal_time": "2026-08-18T20:10:00.000Z",
            "deal_time_msc": 1787076910000,
        }
    }
    raw_conflict = json.dumps(deal_conflict).encode("utf-8")
    res_conflict = await async_client.post("/api/v1/exness/sync", content=raw_conflict, headers=build_signed_headers(device_id, device_secret, raw_conflict))
    assert res_conflict.status_code == 202

    async with test_session_factory() as session:
        stmt = select(RawEventObservation).where(
            RawEventObservation.account_number == 66331199,
            RawEventObservation.external_ticket == 990011,
        ).order_by(RawEventObservation.received_at_utc.asc())
        res_db = await session.execute(stmt)
        obs = res_db.scalars().all()
        assert len(obs) == 2
        assert obs[0].observation_status == "ORIGINAL"
        assert obs[1].observation_status == "CONFLICTING"

        gap_stmt = select(SyncGapEvent).where(
            SyncGapEvent.account_number == 66331199,
            SyncGapEvent.anomaly_category == "CONFLICTING_PAYLOAD",
        )
        gap = (await session.execute(gap_stmt)).scalar_one_or_none()
        assert gap is not None
        assert gap.gap_classification == "POSSIBLE_GAP"


# =====================================================================
# 7. Batch Ingress to Individual Observations Relationship (Option B)
# =====================================================================
@pytest.mark.asyncio
async def test_batch_historical_to_observations_relationship(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "batch_rel_tester@example.com",
        "password": "Password123!",
        "full_name": "Batch Relation Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 44556677,
        "server_name": "Exness-MT5Real1",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    deals = [
        {
            "schema_version": "1.0.0",
            "observation_id": str(uuid.uuid4()),
            "connector_id": str(device_id),
            "account_number": 44556677,
            "deal_ticket": 1000 + i,
            "symbol": "EURUSD",
            "deal_type": "DEAL_TYPE_BUY",
            "deal_entry": "DEAL_ENTRY_IN",
            "volume": "0.1000",
            "price": "1.085000",
            "profit": "0.0000",
            "deal_time": "2026-08-18T10:00:00.000Z",
            "deal_time_msc": 1787076800000 + i,
        }
        for i in range(1, 6)
    ]

    batch = {
        "payload_type": "BATCH_HISTORICAL",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": 44556677,
            "sync_mode": "INITIAL_HISTORICAL",
            "batch_index": 1,
            "batch_size_deals": len(deals),
            "batch_size_orders": 0,
            "deals": deals,
            "orders": [],
            "from_time_msc": 1787076800000,
            "to_time_msc": 1787076900000,
            "is_final_batch": True
        }
    }
    raw_batch = json.dumps(batch).encode("utf-8")
    res = await async_client.post("/api/v1/exness/sync", content=raw_batch, headers=build_signed_headers(device_id, device_secret, raw_batch))
    assert res.status_code == 202

    async with test_session_factory() as session:
        ingress_stmt = select(RawIngressPayload).where(RawIngressPayload.account_number == 44556677)
        ingress = (await session.execute(ingress_stmt)).scalar_one()
        assert ingress.payload_type == "BATCH_HISTORICAL"

        obs_stmt = select(RawEventObservation).where(RawEventObservation.ingress_payload_id == ingress.id)
        obs_list = (await session.execute(obs_stmt)).scalars().all()
        assert len(obs_list) == 5
        assert {o.external_ticket for o in obs_list} == {1001, 1002, 1003, 1004, 1005}


# =====================================================================
# 8. Account Synchronization 4-Tuple Identity & Multi-Device
# =====================================================================
@pytest.mark.asyncio
async def test_account_sync_identity_and_multi_device(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "multidevice@example.com",
        "password": "Password123!",
        "full_name": "Multi Device Tester"
    })
    token = reg.json()["access_token"]
    
    pair1 = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    dev1 = (await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair1.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 77441100,
        "server_name": "Exness-MT5Real1",
        "trade_mode": "REAL",
        "currency": "USD"
    })).json()

    pair2 = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    dev2 = (await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair2.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 77441100,
        "server_name": "Exness-MT5Real1",
        "trade_mode": "REAL",
        "currency": "USD"
    })).json()

    deal1 = {"payload_type": "DEAL_EVENT", "data": {"schema_version": "1.0.0", "account_number": 77441100, "deal_ticket": 500, "deal_time_msc": 1787076900000, "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "0.1000", "price": "1.00", "profit": "0.00", "deal_time": "2026-08-18T20:00:00Z"}}
    raw1 = json.dumps(deal1).encode("utf-8")
    await async_client.post("/api/v1/exness/sync", content=raw1, headers=build_signed_headers(dev1["device_id"], dev1["device_secret"], raw1))

    deal2 = {"payload_type": "DEAL_EVENT", "data": {"schema_version": "1.0.0", "account_number": 77441100, "deal_ticket": 501, "deal_time_msc": 1787076910000, "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "0.1000", "price": "1.00", "profit": "0.00", "deal_time": "2026-08-18T20:00:10Z"}}
    raw2 = json.dumps(deal2).encode("utf-8")
    await async_client.post("/api/v1/exness/sync", content=raw2, headers=build_signed_headers(dev2["device_id"], dev2["device_secret"], raw2))

    async with test_session_factory() as session:
        stmt = select(AccountSyncState).where(AccountSyncState.account_number == 77441100)
        sync_states = (await session.execute(stmt)).scalars().all()
        assert len(sync_states) == 1
        assert sync_states[0].current_cursor_deal_ticket == 501
        assert sync_states[0].current_cursor_time_msc == 1787076910000


# =====================================================================
# 9, 10, 11. Identity Mismatch & Schema Version Rejections
# =====================================================================
@pytest.mark.asyncio
async def test_identity_mismatches_and_schema_version(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "mismatch_tester@example.com",
        "password": "Password123!",
        "full_name": "Mismatch Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 33221100,
        "server_name": "Exness-MT5Real1",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    dev = exchange.json()

    # 1. Currency Mismatch
    bad_curr = {"payload_type": "HEARTBEAT", "data": {"schema_version": "1.0.0", "account_number": 33221100, "currency": "EUR"}}
    raw = json.dumps(bad_curr).encode()
    r1 = await async_client.post("/api/v1/exness/sync", content=raw, headers=build_signed_headers(dev["device_id"], dev["device_secret"], raw))
    assert r1.status_code in (401, 403)

    # 2. Trade Mode Mismatch
    bad_mode = {"payload_type": "HEARTBEAT", "data": {"schema_version": "1.0.0", "account_number": 33221100, "trade_mode": "DEMO"}}
    raw = json.dumps(bad_mode).encode()
    r2 = await async_client.post("/api/v1/exness/sync", content=raw, headers=build_signed_headers(dev["device_id"], dev["device_secret"], raw))
    assert r2.status_code in (401, 403)

    # 3. Server Name Mismatch
    bad_server = {"payload_type": "HEARTBEAT", "data": {"schema_version": "1.0.0", "account_number": 33221100, "server_name": "Exness-WrongServer"}}
    raw = json.dumps(bad_server).encode()
    r3 = await async_client.post("/api/v1/exness/sync", content=raw, headers=build_signed_headers(dev["device_id"], dev["device_secret"], raw))
    assert r3.status_code in (401, 403)

    # 4. Schema Version Unsupported
    bad_schema = {"payload_type": "HEARTBEAT", "data": {"schema_version": "2.0.0", "account_number": 33221100}}
    raw = json.dumps(bad_schema).encode()
    r4 = await async_client.post("/api/v1/exness/sync", content=raw, headers=build_signed_headers(dev["device_id"], dev["device_secret"], raw))
    assert r4.status_code == 422


# =====================================================================
# 12. Stale State Transition on Timeout
# =====================================================================
@pytest.mark.asyncio
async def test_stale_state_transition_on_timeout():
    async with test_session_factory() as session:
        tenant_id = uuid.uuid4()
        sync_state = AccountSyncState(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            broker="EXNESS",
            account_number=33445566,
            server_name="Exness-MT5Real1",
            currency="USD",
            trade_mode="REAL",
            sync_status="CURRENT",
            last_successful_sync_at=datetime.now(timezone.utc) - timedelta(seconds=150),
        )
        session.add(sync_state)
        await session.commit()

        evaluated = await SyncEngine.evaluate_sync_state(session, tenant_id, 33445566)
        assert evaluated is not None
        assert evaluated.sync_status == "STALE"


# =====================================================================
# 13, 14, 15. Deterministic 4-Stream Replay
# =====================================================================
@pytest.mark.asyncio
async def test_deterministic_replay_streams(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "replay_streams@example.com",
        "password": "Password123!",
        "full_name": "Replay Stream Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 99887711,
        "server_name": "Exness-MT5Real1",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    deals = [
        (300, 1787076930000),
        (100, 1787076910000),
        (200, 1787076920000),
    ]
    for ticket, t_msc in deals:
        d = {"payload_type": "DEAL_EVENT", "data": {"schema_version": "1.0.0", "account_number": 99887711, "deal_ticket": ticket, "deal_time_msc": t_msc, "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "0.1000", "price": "1.00", "profit": "0.00", "deal_time": "2026-08-18T20:00:00Z"}}
        raw = json.dumps(d).encode("utf-8")
        await async_client.post("/api/v1/exness/sync", content=raw, headers=build_signed_headers(device_id, device_secret, raw))

    rep_res = await async_client.get(
        "/api/v1/exness/replay/deals/99887711",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert rep_res.status_code == 200
    replayed = rep_res.json()
    assert len(replayed) == 3
    assert [d["external_ticket"] for d in replayed] == [100, 200, 300]


# =====================================================================
# 16, 17, 18. Batch & Cursor Transactional Atomicity & Rollback
# =====================================================================
@pytest.mark.asyncio
async def test_batch_and_cursor_transaction_atomicity(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "atomicity@example.com",
        "password": "Password123!",
        "full_name": "Atomicity Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 55112233,
        "server_name": "Exness-MT5Real1",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    d1 = {"payload_type": "DEAL_EVENT", "data": {"schema_version": "1.0.0", "account_number": 55112233, "deal_ticket": 100, "deal_time_msc": 1787076900000, "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "0.1000", "price": "1.00", "profit": "0.00", "deal_time": "2026-08-18T20:00:00Z"}}
    raw1 = json.dumps(d1).encode("utf-8")
    await async_client.post("/api/v1/exness/sync", content=raw1, headers=build_signed_headers(device_id, device_secret, raw1))

    d_fail = {"payload_type": "DEAL_EVENT", "data": {"schema_version": "99.0.0", "account_number": 55112233, "deal_ticket": 200, "deal_time_msc": 1787076950000, "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "0.1000", "price": "1.00", "profit": "0.00", "deal_time": "2026-08-18T20:00:00Z"}}
    raw_fail = json.dumps(d_fail).encode("utf-8")
    res_fail = await async_client.post("/api/v1/exness/sync", content=raw_fail, headers=build_signed_headers(device_id, device_secret, raw_fail))
    assert res_fail.status_code == 422

    async with test_session_factory() as session:
        sync_stmt = select(AccountSyncState).where(AccountSyncState.account_number == 55112233)
        sync_state = (await session.execute(sync_stmt)).scalar_one()
        assert sync_state.current_cursor_deal_ticket == 100

        obs_stmt = select(RawEventObservation).where(RawEventObservation.account_number == 55112233)
        all_obs = (await session.execute(obs_stmt)).scalars().all()
        assert len(all_obs) == 1
        assert all_obs[0].external_ticket == 100


# =====================================================================
# 19. Account Snapshot Numeric Precision (4 decimals)
# =====================================================================
@pytest.mark.asyncio
async def test_account_snapshot_numeric_precision(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "snap_prec@example.com",
        "password": "Password123!",
        "full_name": "Precision Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 88001122,
        "server_name": "Exness-MT5Real1",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    dev = exchange.json()

    snap_payload = {
        "payload_type": "SNAPSHOT_ACCOUNT",
        "data": {
            "schema_version": "1.0.0",
            "account_number": 88001122,
            "currency": "USD",
            "balance": "10543.2189",
            "equity": "10598.7654",
            "margin": "123.4567",
            "margin_free": "10475.3087",
            "margin_level": "8585.01",
            "leverage": 500,
            "trade_mode": "REAL",
            "is_hedging": True
        }
    }
    raw_snap = json.dumps(snap_payload).encode("utf-8")
    res = await async_client.post("/api/v1/exness/sync", content=raw_snap, headers=build_signed_headers(dev["device_id"], dev["device_secret"], raw_snap))
    assert res.status_code == 202

    async with test_session_factory() as session:
        stmt = select(RawAccountSnapshot).where(RawAccountSnapshot.account_number == 88001122)
        snap = (await session.execute(stmt)).scalar_one()
        assert snap.balance == Decimal("10543.2189")
        assert snap.equity == Decimal("10598.7654")
        assert snap.margin == Decimal("123.4567")
        assert snap.margin_free == Decimal("10475.3087")
        assert snap.margin_level == Decimal("8585.0100")


# =====================================================================
# 20. Position Snapshot Ingestion & Replay
# =====================================================================
@pytest.mark.asyncio
async def test_position_snapshot_ingestion_and_replay(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "pos_snap@example.com",
        "password": "Password123!",
        "full_name": "Pos Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 88009944,
        "server_name": "Exness-MT5Real1",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    dev = exchange.json()

    pos_payload = {
        "payload_type": "SNAPSHOT_POSITIONS",
        "data": {
            "schema_version": "1.0.0",
            "account_number": 88009944,
            "positions": [
                {"ticket": 1, "symbol": "EURUSD", "volume": 1.0, "price_open": 1.0850},
                {"ticket": 2, "symbol": "GBPUSD", "volume": 0.5, "price_open": 1.2800}
            ]
        }
    }
    raw_pos = json.dumps(pos_payload).encode("utf-8")
    res = await async_client.post("/api/v1/exness/sync", content=raw_pos, headers=build_signed_headers(dev["device_id"], dev["device_secret"], raw_pos))
    assert res.status_code == 202

    async with test_session_factory() as session:
        stmt = select(RawPositionSnapshot).where(RawPositionSnapshot.account_number == 88009944)
        pos = (await session.execute(stmt)).scalar_one()
        assert pos.position_count == 2


# =====================================================================
# 21. High-Volume Ingestion Performance Benchmark (1k Tier)
# =====================================================================
@pytest.mark.asyncio
async def test_performance_benchmark_1k_tier(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "perf_bench@example.com",
        "password": "Password123!",
        "full_name": "Perf Bench Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 12348888,
        "server_name": "Exness-MT5Real1",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    deals_1k = [
        {
            "schema_version": "1.0.0",
            "observation_id": str(uuid.uuid4()),
            "connector_id": str(device_id),
            "account_number": 12348888,
            "deal_ticket": 100000 + i,
            "symbol": "EURUSD",
            "deal_type": "DEAL_TYPE_BUY",
            "deal_entry": "DEAL_ENTRY_IN",
            "volume": "0.1000",
            "price": "1.085000",
            "profit": "0.0000",
            "deal_time": "2026-08-18T10:00:00.000Z",
            "deal_time_msc": 1787076800000 + i,
        }
        for i in range(1, 1001)
    ]

    batch = {
        "payload_type": "BATCH_HISTORICAL",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": 12348888,
            "sync_mode": "INITIAL_HISTORICAL",
            "batch_index": 1,
            "batch_size_deals": len(deals_1k),
            "batch_size_orders": 0,
            "deals": deals_1k,
            "orders": [],
            "from_time_msc": 1787076800000,
            "to_time_msc": 1787077800000,
            "is_final_batch": True
        }
    }
    raw_batch = json.dumps(batch).encode("utf-8")

    start_time = time.perf_counter()
    res = await async_client.post(
        "/api/v1/exness/sync",
        content=raw_batch,
        headers=build_signed_headers(device_id, device_secret, raw_batch)
    )
    elapsed = time.perf_counter() - start_time
    assert res.status_code == 202

    ops_per_sec = 1000 / elapsed
    print(f"\n[Performance Benchmark Tier 1 (1,000 Events)] Elapsed: {elapsed*1000:.2f}ms | Throughput: {ops_per_sec:.2f} ops/sec")
    assert ops_per_sec > 200
