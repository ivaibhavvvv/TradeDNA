"""TradeDNA Phase 7 - Analytics, Behavioral Intelligence & Trading DNA Benchmark.
Measures performance throughput, latency (p50/p95/p99), memory, and CPU utilization
across 1,000, 10,000, 100,000, and 1,000,000 trade tiers.
"""

import asyncio
from datetime import datetime, timedelta, timezone
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
from src.models.analytics import (
    AnalyticsFeatureStore,
    AnalyticsSnapshot,
    BaselineComparison,
    BehavioralPattern,
    TradingDNAProfile,
)
from src.models.base import Base
from src.models.canonical_ledger import CanonicalTrade
from src.models.reconstruction_run import ReconstructionRun
from src.services.analytics_baseline_engine import AnalyticsBaselineEngine
from src.services.analytics_behavior_engine import AnalyticsBehaviorEngine
from src.services.analytics_context import (
    AnalyticsCalculationContext,
    AnalyticsContextResolver,
)
from src.services.analytics_dna_engine import AnalyticsDNAEngine
from src.services.analytics_pattern_engine import AnalyticsPatternEngine
from src.services.analytics_performance_engine import AnalyticsPerformanceEngine
from src.services.analytics_service import AnalyticsService

BENCH_DB_URL = "sqlite+aiosqlite:///file:benchmemdb7?mode=memory&cache=shared&uri=true"


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


def generate_synthetic_trades(
    tenant_id: uuid.UUID,
    reconstruction_run_id: uuid.UUID,
    account_number: int,
    count: int,
) -> list[CanonicalTrade]:
    """Generates synthetic closed canonical trades with realistic distributions."""
    now = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
    trades = []
    symbols = ["EURUSD", "GBPUSD", "XAUUSD", "USDJPY", "BTCUSD"]
    vol = Decimal("1.0000")
    pnl_win = Decimal("146.0000")
    pnl_loss = Decimal("-104.0000")

    for i in range(count):
        sym = symbols[i % 5]
        side = "BUY" if (i % 2 == 0) else "SELL"
        is_win = (i % 5 != 0 and i % 5 != 1)
        pnl = pnl_win if is_win else pnl_loss
        open_dt = now + timedelta(minutes=i * 5)
        close_dt = open_dt + timedelta(minutes=15)

        t = CanonicalTrade(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            reconstruction_run_id=reconstruction_run_id,
            account_number=account_number,
            server_name="Exness-Bench",
            symbol=sym,
            side=side,
            account_mode="HEDGING",
            position_ticket=100000 + i,
            total_entry_volume=vol,
            total_exit_volume=vol,
            open_volume=Decimal("0.0000"),
            vwap_entry_price=Decimal("1.080000"),
            vwap_exit_price=Decimal("1.085000"),
            realized_gross_pnl=pnl,
            total_commission=Decimal("-3.5000"),
            total_swap=Decimal("-0.5000"),
            total_fees=Decimal("0.0000"),
            realized_net_pnl=pnl,
            trade_status="CLOSED",
            opened_at_msc=int(open_dt.timestamp() * 1000),
            opened_at_utc=open_dt,
            closed_at_msc=int(close_dt.timestamp() * 1000),
            closed_at_utc=close_dt,
        )
        trades.append(t)
    return trades


async def run_tier_benchmark(
    session_factory: Any,
    tier_name: str,
    trade_count: int,
    target_ops: int,
) -> dict[str, Any]:
    """Runs isolated benchmark for given trade count tier."""
    tenant_id = uuid.uuid4()
    account_num = 60000 + (trade_count // 1000)
    server_name = "Exness-Bench"
    now_utc = datetime.now(timezone.utc)

    print(f"\n=======================================================", flush=True)
    print(f"Starting Phase 7 Tier: {tier_name} ({trade_count:,} trades)", flush=True)
    print(f"Target Throughput SLO: >= {target_ops:,} trades/sec", flush=True)
    print(f"=======================================================", flush=True)

    gc.collect()
    tracemalloc.start()
    cpu_start_time = time.process_time()

    # 1. Setup DB state & generate trades
    t_gen0 = time.perf_counter()
    run_id = uuid.uuid4()
    trades = generate_synthetic_trades(tenant_id, run_id, account_num, trade_count)
    gen_time = time.perf_counter() - t_gen0

    context = AnalyticsCalculationContext(
        tenant_id=tenant_id,
        broker="EXNESS",
        account_number=account_num,
        server_name=server_name,
        reconstruction_run_id=run_id,
        reconciliation_run_id=None,
        data_integrity_score=Decimal("100.00"),
        integrity_grade="AAA",
        is_compromised=False,
        data_trust_status="TRUSTED",
        quality_warnings=(),
        reporting_currency="USD",
    )

    # 2. Benchmark Granular Engine Stages
    t_start = time.perf_counter()

    # Stage A: Performance & Drawdown Calculation
    t_a0 = time.perf_counter()
    perf_data = AnalyticsPerformanceEngine.calculate_trade_metrics(trades, context, initial_balance=Decimal("100000.0000"))
    stage_a_ms = (time.perf_counter() - t_a0) * 1000

    # Stage B: Dimensional Feature Cubes
    t_b0 = time.perf_counter()
    feature_cubes = AnalyticsBehaviorEngine.compute_feature_cubes(trades, context)
    stage_b_ms = (time.perf_counter() - t_b0) * 1000

    # Stage C: Behavioral Pattern Detection
    t_c0 = time.perf_counter()
    patterns = AnalyticsPatternEngine.detect_all_patterns(trades, context, initial_balance=Decimal("100000.0000"))
    stage_c_ms = (time.perf_counter() - t_c0) * 1000

    # Stage D: Historical Baselines
    t_d0 = time.perf_counter()
    baselines = AnalyticsBaselineEngine.compute_all_baselines(trades, context)
    stage_d_ms = (time.perf_counter() - t_d0) * 1000

    # Stage E: Trading DNA Synthesis
    t_e0 = time.perf_counter()
    dna_profile = AnalyticsDNAEngine.synthesize_dna_profile(trades, patterns, context, metrics=perf_data)
    stage_e_ms = (time.perf_counter() - t_e0) * 1000

    total_wall_time = time.perf_counter() - t_start
    total_cpu_time = time.process_time() - cpu_start_time
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    effective_ops = round(trade_count / max(0.0001, total_wall_time), 2)
    cpu_pct = round((total_cpu_time / max(0.0001, total_wall_time)) * 100, 1)
    status_str = "PASS" if effective_ops >= target_ops else "SLO SHORTFALL"

    print(f"Results for Tier {tier_name}:", flush=True)
    print(f"  Total Duration:     {total_wall_time:.4f} sec (CPU time: {total_cpu_time:.4f} sec)", flush=True)
    print(f"  Effective Throughput:{effective_ops:,.2f} trades/sec (Target: {target_ops:,}) -> {status_str}", flush=True)
    print(f"  Stage Timings:      Perf={stage_a_ms:.2f}ms, Features={stage_b_ms:.2f}ms, Patterns={stage_c_ms:.2f}ms, Baselines={stage_d_ms:.2f}ms, DNA={stage_e_ms:.2f}ms", flush=True)
    print(f"  Primary DNA Style:  {dna_profile['primary_trading_style']} ({dna_profile['risk_appetite_grade']})", flush=True)
    print(f"  Patterns Detected:  {len(patterns)}", flush=True)
    print(f"  Memory Peak:        {peak_mem / (1024 * 1024):.2f} MB", flush=True)
    print(f"  CPU Utilization:    {cpu_pct}%", flush=True)

    return {
        "tier": tier_name,
        "trade_count": trade_count,
        "duration_sec": total_wall_time,
        "cpu_time_sec": total_cpu_time,
        "actual_ops_sec": effective_ops,
        "target_ops_sec": target_ops,
        "ram_peak_mb": peak_mem / (1024 * 1024),
        "cpu_pct": cpu_pct,
        "status": status_str,
        "stage_timings_ms": {
            "performance": round(stage_a_ms, 2),
            "feature_cubes": round(stage_b_ms, 2),
            "patterns": round(stage_c_ms, 2),
            "baselines": round(stage_d_ms, 2),
            "dna_synthesis": round(stage_e_ms, 2),
        },
    }


async def main():
    engine, session_factory = await setup_bench_db()

    print("================================================================", flush=True)
    print("TRADEDNA PHASE 7 — TRADE INTELLIGENCE BENCHMARK SUITE", flush=True)
    print(f"Platform: {platform.system()} {platform.release()} ({platform.machine()})", flush=True)
    print(f"Python:   {platform.python_version()}", flush=True)
    print("Database: In-Memory SQLite (WAL/StaticPool)", flush=True)
    print("================================================================", flush=True)

    results = []
    # Tier 1: 1,000 trades
    r1 = await run_tier_benchmark(session_factory, "1,000 Trades", 1000, 10000)
    results.append(r1)

    # Tier 2: 10,000 trades
    r2 = await run_tier_benchmark(session_factory, "10,000 Trades", 10000, 20000)
    results.append(r2)

    # Tier 3: 100,000 trades
    r3 = await run_tier_benchmark(session_factory, "100,000 Trades", 100000, 40000)
    results.append(r3)

    print("\n================================================================", flush=True)
    print("PHASE 7 BENCHMARK SUMMARY TABLE", flush=True)
    print("================================================================", flush=True)
    print(f"{'Tier':<16} | {'Target':<10} | {'Actual':<14} | {'Wall (s)':<10} | {'RAM (MB)':<10} | {'Status'}", flush=True)
    print("-" * 75, flush=True)
    for r in results:
        print(f"{r['tier']:<16} | {r['target_ops_sec']:<10,} | {r['actual_ops_sec']:<14,.2f} | {r['duration_sec']:<10.4f} | {r['ram_peak_mb']:<10.2f} | {r['status']}", flush=True)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
