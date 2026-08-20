"""TradeDNA Phase 8A - Dashboard BFF Performance Benchmark Script.
Measures latency and throughput of the consolidated dashboard overview BFF endpoint.
Target SLO: < 200ms for pre-aggregated authoritative data.
"""

import asyncio
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.abspath("."))

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.models.analytics import AnalyticsSnapshot, TradingDNAProfile
from src.models.base import Base
from src.models.canonical_ledger import CanonicalTrade
from src.models.device import Device
from src.models.raw_event import RawAccountSnapshot, RawIngressPayload
from src.models.reconciliation import ReconciliationRun
from src.models.reconstruction_run import ReconstructionRun
from src.models.sync_state import AccountSyncState
from src.models.tenant import Tenant
from src.models.user import User
from src.services.dashboard_service import DashboardService


async def run_bff_benchmark():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        tenant = Tenant(id=uuid.uuid4(), name="Benchmark Tenant")
        user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="bench@tradedna.io", password_hash="hash", full_name="Bench User")
        session.add_all([tenant, user])

        act_num = 90001
        server_name = "Exness-Real1"
        now_utc = datetime.now(timezone.utc)

        sync = AccountSyncState(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            account_number=act_num,
            server_name=server_name,
            currency="USD",
            trade_mode="REAL",
            sync_status="CURRENT",
            last_successful_sync_at=now_utc,
        )
        session.add(sync)

        device = Device(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            account_number=act_num,
            server_name=server_name,
            trade_mode="REAL",
            currency="USD",
            device_secret="secret",
            device_secret_hash="hash",
            terminal_build=4150,
            connector_version="1.0.0",
            is_active=True,
            last_seen_at=now_utc,
        )
        session.add(device)

        ingress = RawIngressPayload(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            device_id=device.id,
            account_number=act_num,
            server_name=server_name,
            payload_type="ACCOUNT_SNAPSHOT",
            payload_hash="hash",
            raw_payload_bytes=b"{}",
            raw_payload_json={},
            received_at_utc=now_utc,
        )
        session.add(ingress)

        raw_snap = RawAccountSnapshot(
            id=uuid.uuid4(),
            ingress_payload_id=ingress.id,
            tenant_id=tenant.id,
            device_id=device.id,
            account_number=act_num,
            server_name=server_name,
            currency="USD",
            balance=Decimal("25000.0000"),
            equity=Decimal("25420.5000"),
            margin=Decimal("1500.0000"),
            margin_free=Decimal("23920.5000"),
            margin_level=Decimal("1694.7000"),
            leverage=100,
            trade_mode="REAL",
            is_hedging=True,
            raw_payload_json={},
            snapshot_time_utc=now_utc,
            received_at_utc=now_utc,
        )
        session.add(raw_snap)

        recon_run = ReconstructionRun(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            account_number=act_num,
            server_name=server_name,
            status="COMPLETED",
            reason="INITIAL",
            started_at=now_utc,
        )
        session.add(recon_run)
        sync.active_reconstruction_run_id = recon_run.id

        analytics_snap = AnalyticsSnapshot(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            broker="EXNESS",
            account_number=act_num,
            server_name=server_name,
            reconstruction_run_id=recon_run.id,
            period_type="ALL_TIME",
            start_time_utc=now_utc - timedelta(days=30),
            end_time_utc=now_utc,
            total_trades=50,
            winning_trades=32,
            losing_trades=18,
            breakeven_trades=0,
            win_rate=Decimal("0.6400"),
            loss_rate=Decimal("0.3600"),
            gross_profit=Decimal("4500.0000"),
            gross_loss=Decimal("2000.0000"),
            net_pnl=Decimal("2500.0000"),
            profit_factor=Decimal("2.2500"),
            expectancy=Decimal("50.0000"),
            payoff_ratio=Decimal("1.2656"),
            avg_trade=Decimal("50.0000"),
            median_trade=Decimal("45.0000"),
            avg_winner=Decimal("140.6250"),
            avg_loser=Decimal("111.1111"),
            largest_winner=Decimal("350.0000"),
            largest_loser=Decimal("-220.0000"),
            max_drawdown_amount=Decimal("450.0000"),
            max_drawdown_pct=Decimal("0.0350"),
            recovery_factor=Decimal("5.5556"),
            drawdown_duration_sec=3600,
            recovery_duration_sec=7200,
            avg_holding_sec=900,
            median_holding_sec=750,
            avg_winner_holding_sec=800,
            avg_loser_holding_sec=1100,
            duration_ratio=Decimal("1.3750"),
            total_volume_lots=Decimal("25.0000"),
            avg_lot_size=Decimal("0.5000"),
            max_lot_size=Decimal("1.5000"),
            max_consecutive_wins=6,
            max_consecutive_losses=3,
            hhi_symbol_concentration=Decimal("0.4500"),
            top_symbol_volume_pct=Decimal("0.6000"),
            currency="USD",
            is_compromised=False,
            data_integrity_score=Decimal("100.00"),
            integrity_grade="AAA",
            calculation_version="7.0.0",
            metrics_json={},
        )
        session.add(analytics_snap)

        dna = TradingDNAProfile(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            broker="EXNESS",
            account_number=act_num,
            server_name=server_name,
            reconstruction_run_id=recon_run.id,
            primary_trading_style="DAY_TRADER",
            risk_appetite_grade="MODERATE",
            consistency_score=Decimal("88.00"),
            discipline_score=Decimal("92.00"),
            execution_quality_score=Decimal("85.00"),
            favored_instruments=["EURUSD", "XAUUSD"],
            favored_sessions=["LONDON"],
            radar_dimensions={
                "profitability": "85.00",
                "risk_management": "92.00",
                "consistency": "88.00",
                "discipline": "92.00",
                "execution_quality": "85.00",
            },
            top_strengths=["Controlled peak drawdown of 3.5%"],
            top_weaknesses=["Concentrated volume in EURUSD (60%)"],
            behavioral_tendencies=["Prefers London session executions"],
            calculation_version="7.0.0",
            synthesized_at=now_utc,
        )
        session.add(dna)

        recon_audit = ReconciliationRun(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            account_number=act_num,
            server_name=server_name,
            reconstruction_run_id=recon_run.id,
            reconciliation_type="POINT_IN_TIME_SNAPSHOT",
            as_of_time_msc=int(now_utc.timestamp() * 1000),
            as_of_timestamp_utc=now_utc,
            status="COMPLETED",
            data_integrity_score=Decimal("99.80"),
            integrity_grade="AAA",
            is_clean=True,
            discrepancy_count=0,
        )
        session.add(recon_audit)

        # Add 5 canonical trades today
        for i in range(5):
            t = CanonicalTrade(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                reconstruction_run_id=recon_run.id,
                account_number=act_num,
                server_name=server_name,
                symbol="EURUSD",
                side="BUY" if i % 2 == 0 else "SELL",
                account_mode="HEDGING",
                position_ticket=7000 + i,
                total_entry_volume=Decimal("1.0000"),
                total_exit_volume=Decimal("1.0000"),
                open_volume=Decimal("0.0000"),
                vwap_entry_price=Decimal("1.080000"),
                vwap_exit_price=Decimal("1.082500"),
                realized_gross_pnl=Decimal("250.0000"),
                total_commission=Decimal("-3.5000"),
                total_swap=Decimal("0.0000"),
                total_fees=Decimal("0.0000"),
                realized_net_pnl=Decimal("246.5000"),
                trade_status="CLOSED",
                opened_at_msc=int(now_utc.timestamp() * 1000),
                opened_at_utc=now_utc,
                closed_at_msc=int((now_utc + timedelta(minutes=10)).timestamp() * 1000),
                closed_at_utc=now_utc + timedelta(minutes=10),
            )
            session.add(t)

        await session.commit()

        # Warm-up call
        await DashboardService.get_dashboard_overview(session=session, user=user)

        # Benchmark 100 consecutive calls
        latencies = []
        iterations = 100
        for _ in range(iterations):
            t0 = time.perf_counter()
            res = await DashboardService.get_dashboard_overview(session=session, user=user)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)

        p50 = sorted(latencies)[int(iterations * 0.50)]
        p95 = sorted(latencies)[int(iterations * 0.95)]
        p99 = sorted(latencies)[int(iterations * 0.99)]
        avg = sum(latencies) / len(latencies)

        print(f"=== DASHBOARD BFF PERFORMANCE BENCHMARK ({iterations} runs) ===")
        print(f"  Average Latency: {avg:.2f} ms")
        print(f"  P50 Latency:     {p50:.2f} ms")
        print(f"  P95 Latency:     {p95:.2f} ms")
        print(f"  P99 Latency:     {p99:.2f} ms")
        print(f"  SLO Target:      < 200.00 ms")
        print(f"  Status:          {'PASS (SLO Satisfied)' if p95 < 200.0 else 'FAIL'}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_bff_benchmark())
