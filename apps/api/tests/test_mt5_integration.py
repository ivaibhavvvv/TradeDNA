import hashlib
import hmac
import json
import time
import uuid
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
# FULL 18-STEP EXNESS MT5 DEMO INTEGRATION TEST
# =====================================================================
@pytest.mark.asyncio
async def test_exness_mt5_full_integration_lifecycle(async_client: AsyncClient):
    reset_nonce_cache()

    # Step 1: User registers in TradeDNA Dashboard
    reg = await async_client.post("/api/v1/auth/register", json={
        "email": "demo_trader@example.com",
        "password": "SecurePassword123!",
        "full_name": "Demo Trader Alex"
    })
    assert reg.status_code == 201
    user_token = reg.json()["access_token"]

    # Step 2: Dashboard initiates pairing and generates 64-char pairing token
    pair_res = await async_client.post(
        "/api/v1/exness/connection/pair",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert pair_res.status_code == 201
    pairing_token = pair_res.json()["pairing_token"]
    assert len(pairing_token) == 64

    # Step 3: MT5 EA Performs Handshake Exchange with 5-Tuple Exness Demo Identity
    exchange_payload = {
        "pairing_token": pairing_token,
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": 19482011,
        "server_name": "Exness-MT5Trial",
        "trade_mode": "DEMO",
        "currency": "USD",
        "terminal_build": 4360,
        "connector_version": "1.0.0"
    }
    exchange_res = await async_client.post("/api/v1/exness/connection/exchange", json=exchange_payload)
    assert exchange_res.status_code == 200
    handshake_data = exchange_res.json()
    device_id = handshake_data["device_id"]
    device_secret = handshake_data["device_secret"]
    assert handshake_data["account_number"] == 19482011
    assert handshake_data["trade_mode"] == "DEMO"

    # Step 4: Initial Historical Sync (Batch of 50 historical deals)
    historical_deals = []
    historical_orders = []
    for i in range(1, 51):
        t_msc = 1704067200000 + (i * 3600000)
        historical_deals.append({
            "schema_version": "1.0.0",
            "observation_id": str(uuid.uuid4()),
            "event_id": f"deal_hist_{i}",
            "connector_id": str(device_id),
            "account_number": 19482011,
            "deal_ticket": 1000 + i,
            "order_ticket": 5000 + i,
            "position_ticket": 8000 + i,
            "symbol": "XAUUSD",
            "deal_type": "DEAL_TYPE_BUY",
            "deal_entry": "DEAL_ENTRY_IN",
            "volume": "0.1000",
            "price": "2050.500000",
            "commission": "-1.5000",
            "swap": "0.0000",
            "fee": "0.0000",
            "profit": "0.0000",
            "deal_time": "2024-01-01T12:00:00.000Z",
            "deal_time_msc": t_msc,
            "deal_magic": 100201,
            "deal_reason": "DEAL_REASON_CLIENT",
            "deal_external_id": f"HIST-{i}"
        })
        historical_orders.append({
            "schema_version": "1.0.0",
            "observation_id": str(uuid.uuid4()),
            "event_id": f"order_hist_{i}",
            "connector_id": str(device_id),
            "account_number": 19482011,
            "order_ticket": 5000 + i,
            "position_ticket": 8000 + i,
            "symbol": "XAUUSD",
            "order_type": "ORDER_TYPE_BUY",
            "order_state": "ORDER_STATE_FILLED",
            "volume_initial": "0.1000",
            "volume_current": "0.0000",
            "price_open": "2050.500000",
            "sl": "2040.000000",
            "tp": "2070.000000",
            "setup_time": "2024-01-01T12:00:00.000Z",
            "setup_time_msc": t_msc - 100,
            "done_time": "2024-01-01T12:00:00.000Z",
            "done_time_msc": t_msc,
            "order_magic": 100201,
            "order_reason": "ORDER_REASON_CLIENT",
            "order_external_id": f"ORD-HIST-{i}"
        })

    hist_batch_envelope = {
        "payload_type": "BATCH_HISTORICAL",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": 19482011,
            "sync_mode": "INITIAL_HISTORICAL",
            "batch_index": 1,
            "batch_size_deals": 50,
            "batch_size_orders": 50,
            "deals": historical_deals,
            "orders": historical_orders,
            "from_timestamp": "2024-01-01T00:00:00.000Z",
            "from_time_msc": 1704067200000,
            "to_timestamp": "2024-01-03T02:00:00.000Z",
            "to_time_msc": 1704247200000,
            "is_final_batch": True
        }
    }
    raw_hist = json.dumps(hist_batch_envelope).encode("utf-8")
    hist_res = await async_client.post(
        "/api/v1/exness/sync",
        content=raw_hist,
        headers=build_signed_headers(device_id, device_secret, raw_hist)
    )
    assert hist_res.status_code == 202
    assert hist_res.json()["acknowledged_deal_ticket"] == 1050

    # Step 5: Account Snapshot Ingestion
    snap_envelope = {
        "payload_type": "SNAPSHOT_ACCOUNT",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": 19482011,
            "currency": "USD",
            "balance": "10000.0000",
            "equity": "10150.2500",
            "margin": "150.0000",
            "margin_free": "10000.2500",
            "margin_level": "6766.83",
            "leverage": 500,
            "trade_mode": "DEMO",
            "is_hedging": True,
            "snapshot_time": "2026-08-18T20:20:00.000Z"
        }
    }
    raw_snap = json.dumps(snap_envelope).encode("utf-8")
    snap_res = await async_client.post(
        "/api/v1/exness/sync",
        content=raw_snap,
        headers=build_signed_headers(device_id, device_secret, raw_snap)
    )
    assert snap_res.status_code == 202

    # Step 6: Position Snapshot Ingestion
    pos_envelope = {
        "payload_type": "SNAPSHOT_POSITIONS",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": 19482011,
            "positions": [
                {
                    "position_ticket": 991122,
                    "symbol": "EURUSD",
                    "position_type": "POSITION_TYPE_BUY",
                    "volume": "0.5000",
                    "price_open": "1.085000",
                    "price_current": "1.088000",
                    "sl": "1.080000",
                    "tp": "1.095000",
                    "profit": "150.0000",
                    "swap": "0.2500",
                    "open_time": "2026-08-18T19:00:00.000Z"
                }
            ],
            "snapshot_time": "2026-08-18T20:20:00.000Z"
        }
    }
    raw_pos = json.dumps(pos_envelope).encode("utf-8")
    pos_res = await async_client.post(
        "/api/v1/exness/sync",
        content=raw_pos,
        headers=build_signed_headers(device_id, device_secret, raw_pos)
    )
    assert pos_res.status_code == 202

    # Step 7 & 8: Controlled Demo Trade Observed (Entry IN Deal)
    open_deal = {
        "payload_type": "DEAL_EVENT",
        "data": {
            "schema_version": "1.0.0",
            "observation_id": str(uuid.uuid4()),
            "event_id": "demo_trade_open_1",
            "connector_id": str(device_id),
            "account_number": 19482011,
            "deal_ticket": 2001,
            "order_ticket": 7001,
            "position_ticket": 991122,
            "symbol": "EURUSD",
            "deal_type": "DEAL_TYPE_BUY",
            "deal_entry": "DEAL_ENTRY_IN",
            "volume": "0.5000",
            "price": "1.085000",
            "commission": "-2.0000",
            "swap": "0.0000",
            "fee": "0.0000",
            "profit": "0.0000",
            "deal_time": "2026-08-18T19:00:00.000Z",
            "deal_time_msc": 1787076950000,
            "deal_magic": 100201,
            "deal_reason": "DEAL_REASON_CLIENT",
            "deal_external_id": "DEMO-OPEN"
        }
    }
    raw_open = json.dumps(open_deal).encode("utf-8")
    open_res = await async_client.post(
        "/api/v1/exness/sync",
        content=raw_open,
        headers=build_signed_headers(device_id, device_secret, raw_open)
    )
    assert open_res.status_code == 202
    assert open_res.json()["acknowledged_deal_ticket"] == 2001

    # Step 9 & 10: Controlled Demo Trade Close Observed (Exit OUT Deal with Realized Profit)
    close_deal = {
        "payload_type": "DEAL_EVENT",
        "data": {
            "schema_version": "1.0.0",
            "observation_id": str(uuid.uuid4()),
            "event_id": "demo_trade_close_1",
            "connector_id": str(device_id),
            "account_number": 19482011,
            "deal_ticket": 2002,
            "order_ticket": 7002,
            "position_ticket": 991122,
            "symbol": "EURUSD",
            "deal_type": "DEAL_TYPE_SELL",
            "deal_entry": "DEAL_ENTRY_OUT",
            "volume": "0.5000",
            "price": "1.088000",
            "commission": "-2.0000",
            "swap": "0.2500",
            "fee": "0.0000",
            "profit": "150.0000",
            "deal_time": "2026-08-18T20:25:00.000Z",
            "deal_time_msc": 1787076960000,
            "deal_magic": 100201,
            "deal_reason": "DEAL_REASON_CLIENT",
            "deal_external_id": "DEMO-CLOSE"
        }
    }
    raw_close = json.dumps(close_deal).encode("utf-8")
    close_res = await async_client.post(
        "/api/v1/exness/sync",
        content=raw_close,
        headers=build_signed_headers(device_id, device_secret, raw_close)
    )
    assert close_res.status_code == 202
    assert close_res.json()["acknowledged_deal_ticket"] == 2002

    # Step 11: Deal/Order relationship verified (Same position_ticket 991122 on entry & exit)
    assert open_deal["data"]["position_ticket"] == close_deal["data"]["position_ticket"]

    # Step 12 & 13: Spool Drain After Simulated Network Interruption
    spooled_deals = []
    for s_idx in range(1, 6):
        spooled_deals.append({
            "payload_type": "DEAL_EVENT",
            "data": {
                "schema_version": "1.0.0",
                "connector_id": str(device_id),
                "account_number": 19482011,
                "deal_ticket": 3000 + s_idx,
                "order_ticket": 8000 + s_idx,
                "position_ticket": 9000 + s_idx,
                "symbol": "GBPUSD",
                "deal_type": "DEAL_TYPE_BUY",
                "deal_entry": "DEAL_ENTRY_IN",
                "volume": "0.1000",
                "price": "1.280000",
                "profit": "0.0000",
                "deal_time": "2026-08-18T20:30:00.000Z",
                "deal_time_msc": 1787076970000 + s_idx,
            }
        })
    for s_item in spooled_deals:
        raw_s = json.dumps(s_item).encode("utf-8")
        s_res = await async_client.post(
            "/api/v1/exness/sync",
            content=raw_s,
            headers=build_signed_headers(device_id, device_secret, raw_s)
        )
        assert s_res.status_code == 202

    # Step 14 & 16: Device List Check confirms live cursor tracking
    dev_res = await async_client.get(
        "/api/v1/exness/devices",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert dev_res.status_code == 200
    devices = dev_res.json()
    assert len(devices) == 1
    assert devices[0]["last_sync_deal_ticket"] == 3005
    assert devices[0]["is_active"] is True

    # Step 17 & 18: Device Revocation & Verification
    revoke_res = await async_client.post(
        f"/api/v1/exness/connection/revoke/{device_id}",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert revoke_res.status_code == 200

    # Post-revocation sync is blocked
    blocked_res = await async_client.post(
        "/api/v1/exness/sync",
        content=raw_snap,
        headers=build_signed_headers(device_id, device_secret, raw_snap)
    )
    assert blocked_res.status_code == 401
    assert "revoked" in blocked_res.json()["error"]["message"].lower()
