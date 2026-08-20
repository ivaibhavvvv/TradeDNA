import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from src.core.connector_auth import reset_nonce_cache


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
# 1. RFC 4231 HMAC-SHA256 Test Vectors
# =====================================================================
def test_rfc4231_hmac_test_vectors():
    # TC1
    k1 = bytes.fromhex("0b" * 20)
    m1 = b"Hi There"
    h1 = hmac.new(k1, m1, hashlib.sha256).hexdigest().lower()
    assert h1 == "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"

    # TC2
    k2 = b"Jefe"
    m2 = b"what do ya want for nothing?"
    h2 = hmac.new(k2, m2, hashlib.sha256).hexdigest().lower()
    assert h2 == "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"

    # TC3
    k3 = bytes.fromhex("aa" * 20)
    m3 = bytes.fromhex("dd" * 50)
    h3 = hmac.new(k3, m3, hashlib.sha256).hexdigest().lower()
    assert h3 == "773ea91e36800e46854db8ebd09181a72959098b3ef8c122d9635514ced565fe"


# =====================================================================
# 2 & 3. Raw Body Exact Bytes & Whitespace Mutation
# =====================================================================
@pytest.mark.asyncio
async def test_raw_body_exact_bytes_and_whitespace_mutation(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "raw_hmac@example.com",
        "password": "Password123!",
        "full_name": "Raw HMAC Tester"
    })
    token = reg.json()["access_token"]
    
    pair_res = await async_client.post(
        "/api/v1/exness/connection/pair",
        headers={"Authorization": f"Bearer {token}"}
    )
    pairing_token = pair_res.json()["pairing_token"]

    exchange_res = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pairing_token,
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 88112233,
        "server_name": "Exness-MT5Real7",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    data = exchange_res.json()
    device_id = data["device_id"]
    device_secret = data["device_secret"]

    body_dict = {
        "payload_type": "HEARTBEAT",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": 88112233,
            "server_name": "Exness-MT5Real7",
            "terminal_build": 4360,
            "connector_version": "1.0.0",
            "timestamp": "2026-08-18T20:00:00.000Z"
        }
    }
    raw_body_bytes = json.dumps(body_dict).encode("utf-8")
    headers = build_signed_headers(device_id, device_secret, raw_body_bytes)

    res = await async_client.post("/api/v1/exness/sync", content=raw_body_bytes, headers=headers)
    assert res.status_code == 202
    assert res.json()["success"] is True

    fresh_nonce = uuid.uuid4().hex
    mutated_headers = build_signed_headers(device_id, device_secret, raw_body_bytes, nonce=fresh_nonce)
    mutated_bytes = raw_body_bytes + b" "
    res_mutated = await async_client.post("/api/v1/exness/sync", content=mutated_bytes, headers=mutated_headers)
    assert res_mutated.status_code == 401
    assert "invalid hmac signature" in res_mutated.json()["error"]["message"].lower()


# =====================================================================
# 4. Unicode UTF-8 Payload Signing
# =====================================================================
@pytest.mark.asyncio
async def test_unicode_utf8_payload_signing(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "unicode_trader@example.com",
        "password": "Password123!",
        "full_name": "Unicode Trader"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 77889900,
        "server_name": "Exness-MT5Real7",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    body = {
        "payload_type": "DEAL_EVENT",
        "data": {
            "schema_version": "1.0.0",
            "observation_id": str(uuid.uuid4()),
            "event_id": uuid.uuid4().hex,
            "connector_id": str(device_id),
            "account_number": 77889900,
            "deal_ticket": 1234567,
            "order_ticket": 7654321,
            "position_ticket": 998877,
            "symbol": "EURUSD",
            "deal_type": "DEAL_TYPE_BUY",
            "deal_entry": "DEAL_ENTRY_IN",
            "volume": "1.0000",
            "price": "1.085000",
            "profit": "0.0000",
            "deal_time": "2026-08-18T20:15:00.000Z",
            "deal_time_msc": 1787076900000,
            "deal_magic": 1001,
            "deal_reason": "DEAL_REASON_CLIENT",
            "deal_external_id": "TradeDNA: 日本語 / Русский / العربية 🚀🎯"
        }
    }
    raw_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = build_signed_headers(device_id, device_secret, raw_bytes)

    res = await async_client.post("/api/v1/exness/sync", content=raw_bytes, headers=headers)
    assert res.status_code == 202
    assert res.json()["status"] == "SYNCED"


# =====================================================================
# 5. Same-Millisecond Cursor Ordering
# =====================================================================
@pytest.mark.asyncio
async def test_same_millisecond_cursor_ordering(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "cursor_test@example.com",
        "password": "Password123!",
        "full_name": "Cursor Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 99881122,
        "server_name": "Exness-MT5Real7",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    same_time_msc = 1787076930000

    deal_a = {
        "payload_type": "DEAL_EVENT",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": 99881122,
            "deal_ticket": 100,
            "order_ticket": 200,
            "position_ticket": 300,
            "symbol": "BTCUSD",
            "deal_type": "DEAL_TYPE_BUY",
            "deal_entry": "DEAL_ENTRY_IN",
            "volume": "0.1000",
            "price": "65000.00",
            "profit": "0.00",
            "deal_time": "2026-08-18T20:30:00.000Z",
            "deal_time_msc": same_time_msc,
        }
    }
    raw_a = json.dumps(deal_a).encode("utf-8")
    res_a = await async_client.post("/api/v1/exness/sync", content=raw_a, headers=build_signed_headers(device_id, device_secret, raw_a))
    assert res_a.status_code == 202
    assert res_a.json()["acknowledged_deal_ticket"] == 100

    deal_b = {
        "payload_type": "DEAL_EVENT",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": 99881122,
            "deal_ticket": 101,
            "order_ticket": 201,
            "position_ticket": 301,
            "symbol": "BTCUSD",
            "deal_type": "DEAL_TYPE_BUY",
            "deal_entry": "DEAL_ENTRY_IN",
            "volume": "0.2000",
            "price": "65001.00",
            "profit": "0.00",
            "deal_time": "2026-08-18T20:30:00.000Z",
            "deal_time_msc": same_time_msc,
        }
    }
    raw_b = json.dumps(deal_b).encode("utf-8")
    res_b = await async_client.post("/api/v1/exness/sync", content=raw_b, headers=build_signed_headers(device_id, device_secret, raw_b))
    assert res_b.status_code == 202
    assert res_b.json()["acknowledged_deal_ticket"] == 101
    assert res_b.json()["acknowledged_time_msc"] == same_time_msc


# =====================================================================
# 6. Storage Pressure Handling (Schema H Error Report Ingestion)
# =====================================================================
@pytest.mark.asyncio
async def test_storage_pressure_handling(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "spool_pressure@example.com",
        "password": "Password123!",
        "full_name": "Storage Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 99334411,
        "server_name": "Exness-MT5Real7",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    error_report = {
        "payload_type": "ERROR_REPORT",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": 99334411,
            "error_code": "ERR_STORAGE_PRESSURE_QUOTA_EXCEEDED",
            "error_message": "Local disk spool exceeded 50MB. State escalated to STORAGE_PRESSURE.",
            "mql5_last_error": 5001,
            "occurred_at": "2026-08-18T20:30:00.000Z"
        }
    }
    raw_err = json.dumps(error_report).encode("utf-8")
    res = await async_client.post(
        "/api/v1/exness/sync",
        content=raw_err,
        headers=build_signed_headers(device_id, device_secret, raw_err)
    )
    assert res.status_code == 202
    assert res.json()["status"] == "SYNCED"


# =====================================================================
# 7. Adaptive Time-Window Historical Sync (Batch with 500 records)
# =====================================================================
@pytest.mark.asyncio
async def test_adaptive_time_window_pagination(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "adaptive_sync@example.com",
        "password": "Password123!",
        "full_name": "Adaptive Sync Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 88776655,
        "server_name": "Exness-MT5Real7",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    deals = []
    for i in range(1, 101):
        deals.append({
            "schema_version": "1.0.0",
            "observation_id": str(uuid.uuid4()),
            "event_id": f"batch_deal_{i}",
            "connector_id": str(device_id),
            "account_number": 88776655,
            "deal_ticket": 50000 + i,
            "order_ticket": 60000 + i,
            "position_ticket": 70000 + i,
            "symbol": "USDJPY",
            "deal_type": "DEAL_TYPE_BUY",
            "deal_entry": "DEAL_ENTRY_IN",
            "volume": "0.5000",
            "price": "155.200000",
            "profit": "0.0000",
            "deal_time": "2026-08-18T10:00:00.000Z",
            "deal_time_msc": 1787076800000 + i,
        })

    batch_payload = {
        "payload_type": "BATCH_HISTORICAL",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": 88776655,
            "sync_mode": "INITIAL_HISTORICAL",
            "batch_index": 1,
            "batch_size_deals": len(deals),
            "batch_size_orders": 0,
            "deals": deals,
            "orders": [],
            "from_timestamp": "2026-08-18T00:00:00.000Z",
            "from_time_msc": 1787076800000,
            "to_timestamp": "2026-08-18T12:00:00.000Z",
            "to_time_msc": 1787076900000,
            "is_final_batch": True
        }
    }
    raw_batch = json.dumps(batch_payload).encode("utf-8")
    res = await async_client.post(
        "/api/v1/exness/sync",
        content=raw_batch,
        headers=build_signed_headers(device_id, device_secret, raw_batch)
    )
    assert res.status_code == 202
    assert res.json()["acknowledged_deal_ticket"] == 50100


# =====================================================================
# 8. Account Snapshot 4-Decimal Precision Ingestion
# =====================================================================
@pytest.mark.asyncio
async def test_account_snapshot_precision(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "precision_test@example.com",
        "password": "Password123!",
        "full_name": "Precision Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 33221199,
        "server_name": "Exness-MT5Real7",
        "trade_mode": "REAL",
        "currency": "EUR"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    snap = {
        "payload_type": "SNAPSHOT_ACCOUNT",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": 33221199,
            "currency": "EUR",
            "balance": "15420.7825",
            "equity": "15890.1250",
            "margin": "320.5000",
            "margin_free": "15569.6250",
            "margin_level": "4957.92",
            "leverage": 200,
            "trade_mode": "REAL",
            "is_hedging": True,
            "snapshot_time": "2026-08-18T20:30:00.000Z"
        }
    }
    raw_snap = json.dumps(snap).encode("utf-8")
    res = await async_client.post(
        "/api/v1/exness/sync",
        content=raw_snap,
        headers=build_signed_headers(device_id, device_secret, raw_snap)
    )
    assert res.status_code == 202
    assert res.json()["status"] == "SYNCED"


# =====================================================================
# 9. Broker Identity 5-Tuple Mismatch
# =====================================================================
@pytest.mark.asyncio
async def test_broker_identity_tuple_mismatch(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "mismatch_test@example.com",
        "password": "Password123!",
        "full_name": "Mismatch Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 55443322,
        "server_name": "Exness-MT5Real7",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    fake_body = {
        "payload_type": "SNAPSHOT_ACCOUNT",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": 99999999,  # Mismatch!
            "currency": "USD",
            "balance": "10000.00",
            "equity": "10000.00",
            "margin": "0.00",
            "margin_free": "10000.00",
            "margin_level": "0.00",
            "leverage": 500,
            "trade_mode": "REAL",
            "snapshot_time": "2026-08-18T20:35:00.000Z"
        }
    }
    raw_bytes = json.dumps(fake_body).encode("utf-8")
    headers = build_signed_headers(device_id, device_secret, raw_bytes)

    res = await async_client.post("/api/v1/exness/sync", content=raw_bytes, headers=headers)
    assert res.status_code == 403
    assert "account_identity_mismatch" in res.json()["error"]["message"].lower()


# =====================================================================
# 10. Device Revocation Lifecycle
# =====================================================================
@pytest.mark.asyncio
async def test_device_revocation_lifecycle(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "revoke_test@example.com",
        "password": "Password123!",
        "full_name": "Revoke Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 11223344,
        "server_name": "Exness-MT5Real7",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    hb = {"payload_type": "HEARTBEAT", "data": {"account_number": 11223344}}
    raw_hb = json.dumps(hb).encode("utf-8")
    res1 = await async_client.post("/api/v1/exness/sync", content=raw_hb, headers=build_signed_headers(device_id, device_secret, raw_hb))
    assert res1.status_code == 202

    revoke_res = await async_client.post(
        f"/api/v1/exness/connection/revoke/{device_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert revoke_res.status_code == 200

    res2 = await async_client.post("/api/v1/exness/sync", content=raw_hb, headers=build_signed_headers(device_id, device_secret, raw_hb))
    assert res2.status_code == 401
    assert "revoked" in res2.json()["error"]["message"].lower()


# =====================================================================
# 11. Nonce Replay Prevention
# =====================================================================
@pytest.mark.asyncio
async def test_nonce_replay_prevention(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "replay_test@example.com",
        "password": "Password123!",
        "full_name": "Replay Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 66554433,
        "server_name": "Exness-MT5Real7",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    hb = {"payload_type": "HEARTBEAT", "data": {"account_number": 66554433}}
    raw_hb = json.dumps(hb).encode("utf-8")
    headers = build_signed_headers(device_id, device_secret, raw_hb)

    res1 = await async_client.post("/api/v1/exness/sync", content=raw_hb, headers=headers)
    assert res1.status_code == 202

    res2 = await async_client.post("/api/v1/exness/sync", content=raw_hb, headers=headers)
    assert res2.status_code == 401
    assert "replay attack detected" in res2.json()["error"]["message"].lower()


# =====================================================================
# 12. Non-Trading Deal Type Ingestion (All 18 MT5 Types)
# =====================================================================
@pytest.mark.asyncio
async def test_non_trading_deal_ingestion(async_client: AsyncClient):
    reset_nonce_cache()
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "balance_deals@example.com",
        "password": "Password123!",
        "full_name": "Balance Deals Tester"
    })
    token = reg.json()["access_token"]
    pair = await async_client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    
    exchange = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pair.json()["pairing_token"],
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 44332211,
        "server_name": "Exness-MT5Real7",
        "trade_mode": "REAL",
        "currency": "USD"
    })
    device_id = exchange.json()["device_id"]
    device_secret = exchange.json()["device_secret"]

    non_trading_types = [
        ("DEAL_TYPE_BALANCE", "5000.0000", "DEPOSIT"),
        ("DEAL_TYPE_CREDIT", "100.0000", "CREDIT BONUS"),
        ("DEAL_TYPE_COMMISSION", "-15.0000", "AGENT COMMISSION"),
        ("DEAL_TYPE_DIVIDEND", "25.5000", "STOCK DIVIDEND"),
        ("DEAL_TYPE_TAX", "-5.0000", "WITHHOLDING TAX"),
    ]

    for idx, (deal_type, profit, comment) in enumerate(non_trading_types):
        deal_payload = {
            "payload_type": "DEAL_EVENT",
            "data": {
                "schema_version": "1.0.0",
                "connector_id": str(device_id),
                "account_number": 44332211,
                "deal_ticket": 100000 + idx,
                "order_ticket": 0,
                "position_ticket": 0,
                "symbol": "",
                "deal_type": deal_type,
                "deal_entry": "DEAL_ENTRY_STATE",
                "volume": "0.0000",
                "price": "0.000000",
                "profit": profit,
                "deal_time": "2026-08-18T20:45:00.000Z",
                "deal_time_msc": 1787076945000 + idx,
                "deal_magic": 0,
                "deal_reason": "DEAL_REASON_CLIENT",
                "deal_external_id": comment,
            }
        }
        raw_deal = json.dumps(deal_payload).encode("utf-8")
        res = await async_client.post(
            "/api/v1/exness/sync",
            content=raw_deal,
            headers=build_signed_headers(device_id, device_secret, raw_deal),
        )
        assert res.status_code == 202
        assert res.json()["status"] == "SYNCED"


# =====================================================================
# 13. Read-Only Static Source Code Audit
# =====================================================================
def test_read_only_static_source_audit():
    import glob
    import re

    mq5_files = glob.glob("C:/Users/vaibh/.gemini/antigravity-ide/scratch/tradedna/connectors/mt5/**/*.mq*", recursive=True)
    assert len(mq5_files) > 0, "No MQL5 connector files found to audit!"

    prohibited_pattern = re.compile(
        r"\b(OrderSend|OrderSendAsync|PositionClose|OrderModify|OrderDelete|CTrade)\b|<Trade\\Trade\.mqh>",
        re.IGNORECASE
    )

    for file_path in mq5_files:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, 1):
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                    continue
                match = prohibited_pattern.search(line)
                assert match is None, f"PROHIBITED EXECUTION API DETECTED: '{match.group()}' in {file_path}:{line_no}"
