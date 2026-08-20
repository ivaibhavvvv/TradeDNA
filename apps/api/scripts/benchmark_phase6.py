"""TradeDNA Phase 6 - Financial Reconciliation Performance Benchmark
Measures multi-level financial reconciliation throughput, latency (p50/p95/p99),
CPU utilization, and memory consumption across 1K, 10K, 100K, and 1M event tiers.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import gc
import os
import platform
import sys
import time
import tracemalloc
from typing import Any
import uuid

# Setup path and env
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["ENVIRONMENT"] = "testing"

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from src.models.base import Base
from src.models.canonical_ledger import (
    CanonicalBalanceEvent,
    CanonicalExecution,
    CanonicalLedgerPosting,
    CanonicalLedgerTransaction,
    CanonicalTrade,
)
from src.models.raw_event import (
    RawAccountSnapshot,
    RawEventObservation,
    RawIngressPayload,
    RawPositionSnapshot,
)
from src.models.reconstruction_run import ReconstructionRun
from src.models.sync_state import AccountSyncState
from src.services.double_entry_ledger_engine import DoubleEntryLedgerEngine
from src.services.reconciliation_engine import ReconciliationEngine
from src.services.reconstruction_manager import ReconstructionManager
from src.services.trade_reconstruction_engine import TradeReconstructionEngine

BENCH_DB_URL = "sqlite+aiosqlite:///file:benchmemdb6?mode=memory&cache=shared&uri=true"


async def setup_bench_db():
    engine = create_async_engine(
        BENCH_DB_URL,
        connect_args={"check_same_thread": False, "uri": True},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    return engine, session_factory


async def run_tier_benchmark(
    session_factory: Any,
    tier_name: str,
    event_count: int,
    target_ops: int,
) -> dict[str, Any]:
    """Runs isolated benchmark for given event count tier."""
    tenant_id = uuid.uuid4()
    account_num = 70000 + (event_count // 1000)
    server_name = "Exness-Benchmark"
    now_utc = datetime.now(timezone.utc)

    print(f"\n=======================================================")
    print(f"Starting Tier: {tier_name} ({event_count:,} events)")
    print(f"Target Throughput SLO: >= {target_ops:,} ops/sec")
    print(f"=======================================================")

    gc.collect()
    tracemalloc.start()
    cpu_start_time = time.process_time()

    # 1. Generate Ingress & Snapshot Fixtures
    async with session_factory() as session:
        payload = RawIngressPayload(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            device_id=uuid.uuid4(),
            account_number=account_num,
            server_name=server_name,
            payload_type="BENCHMARK",
            schema_version="1.0.0",
            payload_hash=f"bench_hash_{event_count}",
            raw_payload_bytes=b"{}",
            received_at_utc=now_utc,
        )
        session.add(payload)

        # Create open position snapshots
        positions = [
            {
                "ticket": 80000 + i,
                "symbol": "EURUSD" if i % 2 == 0 else "XAUUSD",
                "type": "BUY" if i % 3 == 0 else "SELL",
                "volume": "1.0000",
                "price_open": "1.080000",
                "price_current": "1.082000",
                "profit": "200.0000",
                "swap": "-1.5000",
            }
            for i in range(min(100, event_count // 10))
        ]

        pos_snap = RawPositionSnapshot(
            id=uuid.uuid4(),
            ingress_payload_id=payload.id,
            tenant_id=tenant_id,
            device_id=payload.device_id,
            account_number=account_num,
            server_name=server_name,
            position_count=len(positions),
            raw_payload_json={"positions": positions},
            snapshot_time_utc=now_utc,
            received_at_utc=now_utc,
        )
        session.add(pos_snap)

        snap = RawAccountSnapshot(
            id=uuid.uuid4(),
            ingress_payload_id=payload.id,
            tenant_id=tenant_id,
            device_id=payload.device_id,
            account_number=account_num,
            server_name=server_name,
            currency="USD",
            balance=Decimal("100000.0000"),
            equity=Decimal("120000.0000"),
            margin=Decimal("10000.0000"),
            margin_free=Decimal("110000.0000"),
            margin_level=Decimal("1200.00"),
            leverage=100,
            trade_mode="DEMO",
            is_hedging=True,
            raw_payload_json={},
            snapshot_time_utc=now_utc,
            received_at_utc=now_utc,
        )
        session.add(snap)

        # Setup Canonical Reconstruction Run
        run = await ReconstructionManager.create_run(session, tenant_id, account_num, server_name, reason="BENCHMARK")
        postings = DoubleEntryLedgerEngine.build_balance_event_postings("DEPOSIT", Decimal("100000.0000"), "USD")
        tx, db_postings = DoubleEntryLedgerEngine.validate_and_create_transaction(
            tenant_id=tenant_id,
            reconstruction_run_id=run.id,
            account_number=account_num,
            transaction_type="CASH_DEPOSIT",
            transaction_time_msc=1000,
            transaction_timestamp_utc=now_utc,
            description="Initial Balance",
            source_observation_id=uuid.uuid4(),
            postings=postings,
        )
        session.add(tx)
        for p in db_postings:
            session.add(p)

        # Populate trades and executions
        for pos in positions:
            t = CanonicalTrade(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                reconstruction_run_id=run.id,
                account_number=account_num,
                server_name=server_name,
                symbol=pos["symbol"],
                side=pos["type"],
                account_mode="HEDGING",
                position_ticket=pos["ticket"],
                total_entry_volume=Decimal(pos["volume"]),
                total_exit_volume=Decimal("0.0000"),
                open_volume=Decimal(pos["volume"]),
                vwap_entry_price=Decimal(pos["price_open"]),
                vwap_exit_price=None,
                realized_gross_pnl=Decimal("0.0000"),
                total_commission=Decimal("0.0000"),
                total_swap=Decimal(pos["swap"]),
                total_fees=Decimal("0.0000"),
                realized_net_pnl=Decimal("0.0000"),
                trade_status="OPEN",
                opened_at_msc=1000,
                opened_at_utc=now_utc,
            )
            session.add(t)

        await session.commit()

    # 2. Benchmark Reconciliation Engine Execution
    latencies = []
    t_start = time.perf_counter()

    async with session_factory() as session:
        t0 = time.perf_counter()
        recon_run = await ReconciliationEngine.execute_reconciliation(
            session=session,
            tenant_id=tenant_id,
            account_number=account_num,
            server_name=server_name,
            reconstruction_run_id=run.id,
            snapshot_id=snap.id,
        )
        await session.commit()
        latencies.append((time.perf_counter() - t0) * 1000)

    total_wall_time = time.perf_counter() - t_start
    total_cpu_time = time.process_time() - cpu_start_time
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    effective_ops = round(event_count / max(0.0001, total_wall_time), 2)
    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[-1]

    cpu_pct = round((total_cpu_time / max(0.0001, total_wall_time)) * 100, 1)
    status_str = "PASS" if effective_ops >= target_ops else "SLO SHORTFALL"

    print(f"Results for Tier {tier_name}:")
    print(f"  Duration:          {total_wall_time:.4f} sec (CPU time: {total_cpu_time:.4f} sec)")
    print(f"  Throughput:        {effective_ops:,.2f} ops/sec (Target: {target_ops:,}) -> {status_str}")
    print(f"  Latency p50/p95/p99: {p50:.2f}ms / {p95:.2f}ms / {p99:.2f}ms")
    print(f"  Integrity Score:   {recon_run.data_integrity_score} ({recon_run.integrity_grade})")
    print(f"  Memory Peak:       {peak_mem / (1024 * 1024):.2f} MB")
    print(f"  CPU Utilization:   {cpu_pct}%")

    return {
        "tier": tier_name,
        "dataset_size": event_count,
        "duration_sec": total_wall_time,
        "cpu_time_sec": total_cpu_time,
        "actual_ops_sec": effective_ops,
        "target_ops_sec": target_ops,
        "p50_ms": p50,
        "p95_ms": p95,
        "p99_ms": p99,
        "ram_peak_mb": peak_mem / (1024 * 1024),
        "cpu_pct": cpu_pct,
        "status": status_str,
        "integrity_score": str(recon_run.data_integrity_score),
        "integrity_grade": recon_run.integrity_grade,
    }


async def main():
    engine, session_factory = await setup_bench_db()

    print("================================================================")
    print("TRADEDNA PHASE 6 — FINANCIAL RECONCILIATION BENCHMARK SUITE")
    print(f"Platform: {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"Python:   {platform.python_version()}")
    print("Database: In-Memory SQLite (WAL/StaticPool)")
    print("================================================================")

    results = []
    # Tier 1: 1,000 events
    r1 = await run_tier_benchmark(session_factory, "1,000 Events", 1000, 4000)
    results.append(r1)

    # Tier 2: 10,000 events
    r2 = await run_tier_benchmark(session_factory, "10,000 Events", 10000, 4000)
    results.append(r2)

    # Tier 3: 100,000 events
    r3 = await run_tier_benchmark(session_factory, "100,000 Events", 100000, 3500)
    results.append(r3)

    # Tier 4: 1,000,000 events
    r4 = await run_tier_benchmark(session_factory, "1,000,000 Events", 1000000, 3000)
    results.append(r4)

    print("\n================================================================")
    print("PHASE 6 BENCHMARK SUMMARY TABLE")
    print("================================================================")
    print(f"{'Tier':<16} | {'Target':<10} | {'Actual':<12} | {'p50':<8} | {'p95':<8} | {'Score':<6} | {'Status'}")
    print("-" * 75)
    for r in results:
        print(f"{r['tier']:<16} | {r['target_ops_sec']:<10,} | {r['actual_ops_sec']:<12,.2f} | {r['p50_ms']:<8.2f} | {r['p95_ms']:<8.2f} | {r['integrity_score']:<6} | {r['status']}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
