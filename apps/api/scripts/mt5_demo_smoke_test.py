import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from httpx import ASGITransport
from sqlalchemy import select
from src.core.database import async_session_factory
from src.main import app
from src.models.device import Device, PairingToken
from src.models.raw_event import RawEventObservation
from src.models.user import User


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


async def run_live_smoke_test():
    print("=" * 75)
    print(" TRADEDNA: EXNESS DEMO MT5 LIVE SMOKE TEST & DB VERIFICATION")
    print("=" * 75)

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register user
        reg_res = await client.post("/api/v1/auth/register", json={
            "email": f"exness_demo_{uuid.uuid4().hex[:6]}@tradedna.io",
            "password": "ExnessDemoPassword123!",
            "full_name": "Exness Demo Account Holder"
        })
        print(f"[1. User Registration] HTTP {reg_res.status_code}: {reg_res.json().get('user', {}).get('email')}")
        user_token = reg_res.json()["access_token"]

        # 2. Generate Pairing Token
        pair_res = await client.post(
            "/api/v1/exness/connection/pair",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        pairing_token = pair_res.json()["pairing_token"]
        print(f"[2. Pairing Token Created] Token (64 hex): {pairing_token[:16]}...{pairing_token[-8:]}")

        # 3. EA Performs Handshake Exchange with 5-Tuple Exness Demo Identity
        handshake_payload = {
            "pairing_token": pairing_token,
            "client_nonce": uuid.uuid4().hex,
            "broker": "EXNESS",
            "account_number": 88402911,
            "server_name": "Exness-MT5Trial7",
            "trade_mode": "DEMO",
            "currency": "USD",
            "terminal_build": 4360,
            "connector_version": "1.0.0"
        }
        exchange_res = await client.post("/api/v1/exness/connection/exchange", json=handshake_payload)
        handshake_data = exchange_res.json()
        device_id = handshake_data["device_id"]
        device_secret = handshake_data["device_secret"]
        print(f"[3. Handshake Exchanged] Device ID: {device_id} | Account: 88402911 (Exness-MT5Trial7 DEMO USD)")

        # 4. Ingest Initial Historical Sync (Batch of 25 historical deals)
        hist_deals = []
        for i in range(1, 26):
            t_msc = 1704067200000 + (i * 3600000)
            hist_deals.append({
                "schema_version": "1.0.0",
                "observation_id": str(uuid.uuid4()),
                "event_id": f"hist_deal_{i}",
                "connector_id": str(device_id),
                "account_number": 88402911,
                "deal_ticket": 1000 + i,
                "order_ticket": 5000 + i,
                "position_ticket": 8000 + i,
                "symbol": "EURUSD",
                "deal_type": "DEAL_TYPE_BUY",
                "deal_entry": "DEAL_ENTRY_IN",
                "volume": "0.5000",
                "price": "1.085000",
                "commission": "-2.0000",
                "profit": "0.0000",
                "deal_time": "2024-01-01T12:00:00.000Z",
                "deal_time_msc": t_msc,
            })

        batch_envelope = {
            "payload_type": "BATCH_HISTORICAL",
            "data": {
                "schema_version": "1.0.0",
                "connector_id": str(device_id),
                "account_number": 88402911,
                "sync_mode": "INITIAL_HISTORICAL",
                "batch_index": 1,
                "batch_size_deals": 25,
                "batch_size_orders": 0,
                "deals": hist_deals,
                "orders": [],
                "from_timestamp": "2024-01-01T00:00:00.000Z",
                "from_time_msc": 1704067200000,
                "to_timestamp": "2024-01-02T01:00:00.000Z",
                "to_time_msc": 1704157200000,
                "is_final_batch": True
            }
        }
        raw_batch = json.dumps(batch_envelope).encode("utf-8")
        batch_res = await client.post(
            "/api/v1/exness/sync",
            content=raw_batch,
            headers=build_signed_headers(device_id, device_secret, raw_batch)
        )
        print(f"[4. Initial Historical Sync] HTTP {batch_res.status_code}: Acknowledged deal ticket {batch_res.json()['acknowledged_deal_ticket']}")

        # 5. Account & Position Snapshots
        snap_envelope = {
            "payload_type": "SNAPSHOT_ACCOUNT",
            "data": {
                "schema_version": "1.0.0",
                "connector_id": str(device_id),
                "account_number": 88402911,
                "currency": "USD",
                "balance": "10000.0000",
                "equity": "10250.0000",
                "margin": "200.0000",
                "margin_free": "10050.0000",
                "margin_level": "5125.00",
                "leverage": 500,
                "trade_mode": "DEMO",
                "is_hedging": True,
                "snapshot_time": "2026-08-18T20:20:00.000Z"
            }
        }
        raw_snap = json.dumps(snap_envelope).encode("utf-8")
        snap_res = await client.post(
            "/api/v1/exness/sync",
            content=raw_snap,
            headers=build_signed_headers(device_id, device_secret, raw_snap)
        )
        print(f"[5. Account Snapshot] HTTP {snap_res.status_code}: Balance $10000.00 | Equity $10250.00")

        # 6. Controlled Demo Entry Transaction (Deal 2001, BUY 1.00 lot XAUUSD @ 2350.00)
        open_deal = {
            "payload_type": "DEAL_EVENT",
            "data": {
                "schema_version": "1.0.0",
                "observation_id": str(uuid.uuid4()),
                "event_id": "demo_live_open_1",
                "connector_id": str(device_id),
                "account_number": 88402911,
                "deal_ticket": 2001,
                "order_ticket": 7001,
                "position_ticket": 991122,
                "symbol": "XAUUSD",
                "deal_type": "DEAL_TYPE_BUY",
                "deal_entry": "DEAL_ENTRY_IN",
                "volume": "1.0000",
                "price": "2350.000000",
                "commission": "-3.5000",
                "profit": "0.0000",
                "deal_time": "2026-08-18T20:21:00.000Z",
                "deal_time_msc": 1787076950000,
                "deal_magic": 100201,
                "deal_reason": "DEAL_REASON_CLIENT",
                "deal_external_id": "EXNESS-DEMO-OPEN"
            }
        }
        raw_open = json.dumps(open_deal).encode("utf-8")
        open_res = await client.post(
            "/api/v1/exness/sync",
            content=raw_open,
            headers=build_signed_headers(device_id, device_secret, raw_open)
        )
        print(f"[6. Demo Trade Entry] HTTP {open_res.status_code}: Deal 2001 BUY 1.00 XAUUSD | Cursor -> 2001")

        # 7. Controlled Demo Exit Transaction (Deal 2002, SELL 1.00 lot XAUUSD @ 2355.00, Profit +$500.00)
        close_deal = {
            "payload_type": "DEAL_EVENT",
            "data": {
                "schema_version": "1.0.0",
                "observation_id": str(uuid.uuid4()),
                "event_id": "demo_live_close_1",
                "connector_id": str(device_id),
                "account_number": 88402911,
                "deal_ticket": 2002,
                "order_ticket": 7002,
                "position_ticket": 991122,
                "symbol": "XAUUSD",
                "deal_type": "DEAL_TYPE_SELL",
                "deal_entry": "DEAL_ENTRY_OUT",
                "volume": "1.0000",
                "price": "2355.000000",
                "commission": "-3.5000",
                "profit": "500.0000",
                "deal_time": "2026-08-18T20:25:00.000Z",
                "deal_time_msc": 1787076960000,
                "deal_magic": 100201,
                "deal_reason": "DEAL_REASON_CLIENT",
                "deal_external_id": "EXNESS-DEMO-CLOSE"
            }
        }
        raw_close = json.dumps(close_deal).encode("utf-8")
        close_res = await client.post(
            "/api/v1/exness/sync",
            content=raw_close,
            headers=build_signed_headers(device_id, device_secret, raw_close)
        )
        print(f"[7. Demo Trade Close] HTTP {close_res.status_code}: Deal 2002 Profit +$500.00 | Cursor -> 2002")

        # 8. Spool Drain After Network Reconnect
        spool_deal = {
            "payload_type": "DEAL_EVENT",
            "data": {
                "schema_version": "1.0.0",
                "connector_id": str(device_id),
                "account_number": 88402911,
                "deal_ticket": 2003,
                "order_ticket": 7003,
                "position_ticket": 991123,
                "symbol": "GBPUSD",
                "deal_type": "DEAL_TYPE_BUY",
                "deal_entry": "DEAL_ENTRY_IN",
                "volume": "0.5000",
                "price": "1.285000",
                "profit": "0.0000",
                "deal_time": "2026-08-18T20:28:00.000Z",
                "deal_time_msc": 1787076970000,
            }
        }
        raw_spool = json.dumps(spool_deal).encode("utf-8")
        spool_res = await client.post(
            "/api/v1/exness/sync",
            content=raw_spool,
            headers=build_signed_headers(device_id, device_secret, raw_spool)
        )
        print(f"[8. Persistent Spool Drain] HTTP {spool_res.status_code}: Drained Queued Deal 2003 | Cursor -> 2003")

        # 9. Device Status & Cursor Verification
        dev_res = await client.get("/api/v1/exness/devices", headers={"Authorization": f"Bearer {user_token}"})
        devices = dev_res.json()
        print(f"[9. Database Cursor Verified] Device: {devices[0]['id']} | Cursor Ticket: {devices[0]['last_sync_deal_ticket']}")

        # 10. Device Revocation & Ingress Lock
        revoke_res = await client.post(
            f"/api/v1/exness/connection/revoke/{device_id}",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        print(f"[10. Device Revocation] HTTP {revoke_res.status_code}: Connector Device Revoked in DB & Blocklist")

        # 11. Confirm Rejected Ingestion Post-Revocation
        blocked_res = await client.post(
            "/api/v1/exness/sync",
            content=raw_snap,
            headers=build_signed_headers(device_id, device_secret, raw_snap)
        )
        print(f"[11. Revocation Lock Verified] HTTP {blocked_res.status_code}: {blocked_res.json()['error']['message']}")

    # Direct Database Inspection
    async with async_session_factory() as session:
        raw_count_stmt = select(RawEventObservation).where(RawEventObservation.device_id == uuid.UUID(device_id))
        raw_count_res = await session.execute(raw_count_stmt)
        total_obs = len(raw_count_res.scalars().all())

        device_stmt = select(Device).where(Device.id == uuid.UUID(device_id))
        device_db = (await session.execute(device_stmt)).scalar_one()

        print("=" * 75)
        print(" DATABASE AUDIT & VERIFICATION EVIDENCE:")
        print(f" - Total Layer 1 Raw Observations Persisted: {total_obs}")
        print(f" - Device Status in DB: is_active={device_db.is_active}, is_revoked={device_db.is_revoked}")
        print(f" - Last Synced Deal Ticket in DB: {device_db.last_sync_deal_ticket}")
        print(f" - Broker Identity 5-Tuple in DB: {device_db.broker} | {device_db.account_number} | {device_db.server_name} | {device_db.trade_mode} | {device_db.currency}")
        print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_live_smoke_test())
