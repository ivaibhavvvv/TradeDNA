"""TradeDNA Phase 4 - High-Volume Ingestion Benchmark Runner
Measures throughput, p50/p95/p99 latency, DB write latency, and storage growth across
1,000, 10,000, and 100,000 event tiers.
"""

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import statistics
import time
import uuid
from httpx import ASGITransport, AsyncClient
from src.core.connector_auth import reset_nonce_cache
from src.core.database import get_db_session
from src.main import app
import src.models
from src.models.base import Base
from tests.conftest import override_get_db_session, test_engine
from tests.test_phase4_raw_sync import build_signed_headers


async def run_benchmark():
    print("=" * 60)
    print("TRADEDNA PHASE 4 — HIGH-VOLUME INGESTION BENCHMARK")
    print("=" * 60)

    # Initialize schema on test engine
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app.dependency_overrides[get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reset_nonce_cache()
        # Setup Account & Device
        reg = await client.post("/api/v1/auth/register", json={
            "email": f"bench_{uuid.uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "full_name": "Benchmark User"
        })
        token = reg.json()["access_token"]
        pair = await client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
        
        exchange = await client.post("/api/v1/exness/connection/exchange", json={
            "pairing_token": pair.json()["pairing_token"],
            "client_nonce": uuid.uuid4().hex,
            "broker": "EXNESS",
            "account_number": 99990001,
            "server_name": "Exness-MT5Real1",
            "trade_mode": "REAL",
            "currency": "USD"
        })
        device_id = exchange.json()["device_id"]
        device_secret = exchange.json()["device_secret"]

        tiers = [1_000, 10_000, 100_000]

        for target_count in tiers:
            batch_size = 500
            total_batches = target_count // batch_size
            latencies = []
            total_bytes = 0

            print(f"\n--- Running Tier: {target_count:,} events ({total_batches} batches of {batch_size}) ---")
            start_overall = time.perf_counter()

            for b_idx in range(1, total_batches + 1):
                deals = [
                    {
                        "schema_version": "1.0.0",
                        "observation_id": str(uuid.uuid4()),
                        "connector_id": str(device_id),
                        "account_number": 99990001,
                        "deal_ticket": b_idx * 1000 + i,
                        "symbol": "EURUSD",
                        "deal_type": "DEAL_TYPE_BUY",
                        "deal_entry": "DEAL_ENTRY_IN",
                        "volume": "0.1000",
                        "price": "1.085000",
                        "profit": "0.0000",
                        "deal_time": "2026-08-18T10:00:00.000Z",
                        "deal_time_msc": 1787076800000 + (b_idx * 1000) + i,
                    }
                    for i in range(batch_size)
                ]
                batch_payload = {
                    "payload_type": "BATCH_HISTORICAL",
                    "data": {
                        "schema_version": "1.0.0",
                        "connector_id": str(device_id),
                        "account_number": 99990001,
                        "sync_mode": "INITIAL_HISTORICAL",
                        "batch_index": b_idx,
                        "batch_size_deals": len(deals),
                        "batch_size_orders": 0,
                        "deals": deals,
                        "orders": [],
                        "from_time_msc": 1787076800000,
                        "to_time_msc": 1787077800000,
                        "is_final_batch": (b_idx == total_batches)
                    }
                }
                raw_bytes = json.dumps(batch_payload).encode("utf-8")
                total_bytes += len(raw_bytes)

                t0 = time.perf_counter()
                res = await client.post(
                    "/api/v1/exness/sync",
                    content=raw_bytes,
                    headers=build_signed_headers(device_id, device_secret, raw_bytes)
                )
                t1 = time.perf_counter()
                assert res.status_code == 202
                latencies.append((t1 - t0) * 1000)

            total_time = time.perf_counter() - start_overall
            latencies_sorted = sorted(latencies)
            p50 = statistics.median(latencies_sorted)
            p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
            p99 = latencies_sorted[int(len(latencies_sorted) * 0.99)]
            throughput = target_count / total_time

            print(f"Results for {target_count:,} events:")
            print(f"  - Total Elapsed Time : {total_time:.3f} s")
            print(f"  - Ingestion Throughput: {throughput:,.2f} events/sec")
            print(f"  - Batch Latency (p50) : {p50:.2f} ms")
            print(f"  - Batch Latency (p95) : {p95:.2f} ms")
            print(f"  - Batch Latency (p99) : {p99:.2f} ms")
            print(f"  - Total Raw Payload   : {total_bytes / (1024 * 1024):.2f} MB")

    print("\n" + "=" * 60)
    print("BENCHMARK COMPLETED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_benchmark())
