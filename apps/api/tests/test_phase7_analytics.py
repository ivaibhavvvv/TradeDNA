"""TradeDNA Phase 7 - Analytics, Behavioral Intelligence & Trading DNA Test Suite.
Comprehensive verification of deterministic performance metrics, drawdowns,
behavioral pattern detectors, Trading DNA profiles, baselines, and tenant isolation.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
import uuid
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.security import create_access_token
from src.models.analytics import (
    AnalyticsFeatureStore,
    AnalyticsSnapshot,
    BaselineComparison,
    BehavioralPattern,
    TradingDNAProfile,
)
from src.models.canonical_ledger import CanonicalTrade
from src.models.reconciliation import ReconciliationRun
from src.models.reconstruction_run import ReconstructionRun
from src.models.sync_state import AccountSyncState
from src.models.tenant import Tenant
from src.models.user import User
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


def make_trade(
    tenant_id: uuid.UUID,
    reconstruction_run_id: uuid.UUID,
    account_number: int = 10001,
    symbol: str = "EURUSD",
    side: str = "BUY",
    open_volume: str = "1.0000",
    pnl: str = "100.0000",
    opened_at: Optional[datetime] = None,
    closed_at: Optional[datetime] = None,
    position_ticket: int = 1001,
) -> CanonicalTrade:
    now = datetime.now(timezone.utc)
    o_dt = opened_at or now
    c_dt = closed_at or (o_dt + timedelta(minutes=15))
    return CanonicalTrade(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        reconstruction_run_id=reconstruction_run_id,
        account_number=account_number,
        server_name="Exness-Real",
        symbol=symbol,
        side=side,
        account_mode="HEDGING",
        position_ticket=position_ticket,
        total_entry_volume=Decimal(open_volume),
        total_exit_volume=Decimal(open_volume),
        open_volume=Decimal("0.0000"),
        vwap_entry_price=Decimal("1.080000"),
        vwap_exit_price=Decimal("1.085000"),
        realized_gross_pnl=Decimal(pnl),
        total_commission=Decimal("0.0000"),
        total_swap=Decimal("0.0000"),
        total_fees=Decimal("0.0000"),
        realized_net_pnl=Decimal(pnl),
        trade_status="CLOSED",
        opened_at_msc=int(o_dt.timestamp() * 1000),
        opened_at_utc=o_dt,
        closed_at_msc=int(c_dt.timestamp() * 1000),
        closed_at_utc=c_dt,
    )


# ==============================================================================
# 1. PERFORMANCE & DRAWDOWN FORMULA TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_performance_analytics_formulas():
    """Verifies exact deterministic performance formulas: win rate, PF, expectancy, payoff."""
    tenant_id = uuid.uuid4()
    run_id = uuid.uuid4()
    base_time = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)

    # 4 trades: Win +$200, Win +$100, Loss -$100, Breakeven $0
    trades = [
        make_trade(tenant_id, run_id, pnl="200.0000", opened_at=base_time, closed_at=base_time + timedelta(minutes=10)),
        make_trade(tenant_id, run_id, pnl="100.0000", opened_at=base_time + timedelta(minutes=15), closed_at=base_time + timedelta(minutes=25)),
        make_trade(tenant_id, run_id, pnl="-100.0000", opened_at=base_time + timedelta(minutes=30), closed_at=base_time + timedelta(minutes=45)),
        make_trade(tenant_id, run_id, pnl="0.0000", opened_at=base_time + timedelta(minutes=50), closed_at=base_time + timedelta(minutes=55)),
    ]

    context = AnalyticsCalculationContext(
        tenant_id=tenant_id, broker="EXNESS", account_number=10001, server_name="Exness-Real",
        reconstruction_run_id=run_id, reconciliation_run_id=None,
        data_integrity_score=Decimal("100.00"), integrity_grade="AAA", is_compromised=False,
        data_trust_status="TRUSTED", quality_warnings=(), reporting_currency="USD",
    )

    metrics = AnalyticsPerformanceEngine.calculate_trade_metrics(trades, context, initial_balance=Decimal("10000.0000"))

    assert metrics["total_trades"] == 4
    assert metrics["winning_trades"] == 2
    assert metrics["losing_trades"] == 1
    assert metrics["breakeven_trades"] == 1
    assert metrics["win_rate"] == Decimal("0.5000")
    assert metrics["loss_rate"] == Decimal("0.2500")
    assert metrics["gross_profit"] == Decimal("300.0000")
    assert metrics["gross_loss"] == Decimal("100.0000")
    assert metrics["net_pnl"] == Decimal("200.0000")
    assert metrics["profit_factor"] == Decimal("3.0000")
    assert metrics["avg_winner"] == Decimal("150.0000")
    assert metrics["avg_loser"] == Decimal("100.0000")
    assert metrics["payoff_ratio"] == Decimal("1.5000")
    assert metrics["expectancy"] == Decimal("50.0000")
    assert metrics["largest_winner"] == Decimal("200.0000")
    assert metrics["largest_loser"] == Decimal("-100.0000")
    assert metrics["max_consecutive_wins"] == 2
    assert metrics["max_consecutive_losses"] == 1


@pytest.mark.asyncio
async def test_edge_cases_zero_and_perfect_accounts():
    """Verifies edge case handling for 0-trade, 100% win, and 100% loss accounts."""
    tenant_id = uuid.uuid4()
    run_id = uuid.uuid4()
    context = AnalyticsCalculationContext(
        tenant_id=tenant_id, broker="EXNESS", account_number=10001, server_name="Exness-Real",
        reconstruction_run_id=run_id, reconciliation_run_id=None,
        data_integrity_score=Decimal("100.00"), integrity_grade="AAA", is_compromised=False,
        data_trust_status="TRUSTED", quality_warnings=(), reporting_currency="USD",
    )

    # 1. Zero-trade account
    m_zero = AnalyticsPerformanceEngine.calculate_trade_metrics([], context)
    assert m_zero["total_trades"] == 0
    assert m_zero["net_pnl"] == Decimal("0.0000")
    assert m_zero["win_rate"] == Decimal("0.0000")

    # 2. 100% win account (Zero loss)
    t_win = [make_trade(tenant_id, run_id, pnl="150.0000"), make_trade(tenant_id, run_id, pnl="50.0000")]
    m_win = AnalyticsPerformanceEngine.calculate_trade_metrics(t_win, context, initial_balance=Decimal("1000.0000"))
    assert m_win["win_rate"] == Decimal("1.0000")
    assert m_win["profit_factor"] == Decimal("999.9900")
    assert m_win["max_drawdown_amount"] == Decimal("0.0000")

    # 3. 100% loss account (Zero profit)
    t_loss = [make_trade(tenant_id, run_id, pnl="-50.0000"), make_trade(tenant_id, run_id, pnl="-100.0000")]
    m_loss = AnalyticsPerformanceEngine.calculate_trade_metrics(t_loss, context, initial_balance=Decimal("1000.0000"))
    assert m_loss["win_rate"] == Decimal("0.0000")
    assert m_loss["loss_rate"] == Decimal("1.0000")
    assert m_loss["profit_factor"] == Decimal("0.0000")
    assert m_loss["max_drawdown_amount"] == Decimal("150.0000")


# ==============================================================================
# 2. DIMENSIONAL FEATURE STORE & SESSIONS
# ==============================================================================

@pytest.mark.asyncio
async def test_session_and_symbol_dimensional_cubes():
    """Verifies dimensional slicing across Asian, London, and New York sessions and symbols."""
    tenant_id = uuid.uuid4()
    run_id = uuid.uuid4()

    # Trade 1: Asian Session (04:00 UTC) on EURUSD
    t1 = make_trade(tenant_id, run_id, symbol="EURUSD", pnl="100.0000", opened_at=datetime(2026, 8, 1, 4, 0, 0, tzinfo=timezone.utc))
    # Trade 2: London Session (10:00 UTC) on XAUUSD
    t2 = make_trade(tenant_id, run_id, symbol="XAUUSD", pnl="-50.0000", opened_at=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc))
    # Trade 3: New York Session (15:00 UTC) on EURUSD
    t3 = make_trade(tenant_id, run_id, symbol="EURUSD", pnl="80.0000", opened_at=datetime(2026, 8, 1, 15, 0, 0, tzinfo=timezone.utc))

    context = AnalyticsCalculationContext(
        tenant_id=tenant_id, broker="EXNESS", account_number=10001, server_name="Exness-Real",
        reconstruction_run_id=run_id, reconciliation_run_id=None,
        data_integrity_score=Decimal("100.00"), integrity_grade="AAA", is_compromised=False,
        data_trust_status="TRUSTED", quality_warnings=(), reporting_currency="USD",
    )

    cubes = AnalyticsBehaviorEngine.compute_feature_cubes([t1, t2, t3], context)

    # Check EURUSD symbol cube
    eur_cube = next(c for c in cubes if c["dimension_type"] == "SYMBOL" and c["dimension_key"] == "EURUSD")
    assert eur_cube["trade_count"] == 2
    assert eur_cube["win_count"] == 2
    assert eur_cube["net_pnl"] == Decimal("180.0000")

    # Check Asian session cube
    asian_cube = next(c for c in cubes if c["dimension_type"] == "SESSION" and c["dimension_key"] == "ASIAN")
    assert asian_cube["trade_count"] == 1
    assert asian_cube["net_pnl"] == Decimal("100.0000")


# ==============================================================================
# 3. BEHAVIORAL PATTERN DETECTORS
# ==============================================================================

@pytest.mark.asyncio
async def test_revenge_trading_detector_and_false_positive_control():
    """Verifies revenge trading detection on rapid volume escalation after a loss,
    and ensures NO trigger after a winning trade."""
    tenant_id = uuid.uuid4()
    run_id = uuid.uuid4()
    base_time = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Case 1: True Positive - Loss of -$200, followed 45s later by 2.0x volume trade
    t_loss = make_trade(tenant_id, run_id, open_volume="1.0000", pnl="-200.0000", opened_at=base_time, closed_at=base_time + timedelta(minutes=5))
    t_revenge = make_trade(tenant_id, run_id, open_volume="2.0000", pnl="50.0000", opened_at=base_time + timedelta(minutes=5, seconds=45), closed_at=base_time + timedelta(minutes=15))

    context = AnalyticsCalculationContext(
        tenant_id=tenant_id, broker="EXNESS", account_number=10001, server_name="Exness-Real",
        reconstruction_run_id=run_id, reconciliation_run_id=None,
        data_integrity_score=Decimal("100.00"), integrity_grade="AAA", is_compromised=False,
        data_trust_status="TRUSTED", quality_warnings=(), reporting_currency="USD",
    )

    patterns = AnalyticsPatternEngine.detect_all_patterns([t_loss, t_revenge], context)
    rev_pat = [p for p in patterns if p["pattern_type"] == "POSSIBLE_REVENGE_TRADING"]
    assert len(rev_pat) == 1
    assert rev_pat[0]["severity"] == "CRITICAL"
    assert rev_pat[0]["evidence_payload"]["inter_trade_seconds"] == 45

    # Case 2: False Positive Control - Win of +$200 followed by 2.0x volume trade (should NOT trigger revenge trading)
    t_win = make_trade(tenant_id, run_id, open_volume="1.0000", pnl="200.0000", opened_at=base_time, closed_at=base_time + timedelta(minutes=5))
    t_scale = make_trade(tenant_id, run_id, open_volume="2.0000", pnl="50.0000", opened_at=base_time + timedelta(minutes=5, seconds=45), closed_at=base_time + timedelta(minutes=15))

    pats_win = AnalyticsPatternEngine.detect_all_patterns([t_win, t_scale], context)
    assert not any(p["pattern_type"] == "POSSIBLE_REVENGE_TRADING" for p in pats_win)


@pytest.mark.asyncio
async def test_loss_escalation_martingale_detector():
    """Verifies detection of position-size escalation / Martingale on consecutive losing streaks."""
    tenant_id = uuid.uuid4()
    run_id = uuid.uuid4()
    t0 = datetime(2026, 8, 1, 14, 0, 0, tzinfo=timezone.utc)

    # 3 consecutive losses with escalating lot sizes: 0.1 -> 0.2 -> 0.5
    trades = [
        make_trade(tenant_id, run_id, open_volume="0.1000", pnl="-50.0000", opened_at=t0, closed_at=t0 + timedelta(minutes=10)),
        make_trade(tenant_id, run_id, open_volume="0.2000", pnl="-100.0000", opened_at=t0 + timedelta(minutes=15), closed_at=t0 + timedelta(minutes=25)),
        make_trade(tenant_id, run_id, open_volume="0.5000", pnl="-250.0000", opened_at=t0 + timedelta(minutes=30), closed_at=t0 + timedelta(minutes=40)),
    ]

    context = AnalyticsCalculationContext(
        tenant_id=tenant_id, broker="EXNESS", account_number=10001, server_name="Exness-Real",
        reconstruction_run_id=run_id, reconciliation_run_id=None,
        data_integrity_score=Decimal("100.00"), integrity_grade="AAA", is_compromised=False,
        data_trust_status="TRUSTED", quality_warnings=(), reporting_currency="USD",
    )

    patterns = AnalyticsPatternEngine.detect_all_patterns(trades, context)
    martingale_pat = [p for p in patterns if p["pattern_type"] == "POSSIBLE_LOSS_ESCALATION"]
    assert len(martingale_pat) == 1
    assert martingale_pat[0]["evidence_payload"]["consecutive_losing_trades"] == 3


@pytest.mark.asyncio
async def test_loser_holding_and_winner_cutting_patterns():
    """Verifies detection of disposition effect (holding losers significantly longer than winners)."""
    tenant_id = uuid.uuid4()
    run_id = uuid.uuid4()
    t0 = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)

    # 3 quick winners (held for 5 minutes / 300s each)
    w1 = make_trade(tenant_id, run_id, pnl="100.0000", opened_at=t0, closed_at=t0 + timedelta(minutes=5))
    w2 = make_trade(tenant_id, run_id, pnl="120.0000", opened_at=t0 + timedelta(minutes=10), closed_at=t0 + timedelta(minutes=15))
    w3 = make_trade(tenant_id, run_id, pnl="90.0000", opened_at=t0 + timedelta(minutes=20), closed_at=t0 + timedelta(minutes=25))
    # 2 losers: one normal (5 min), one prolonged (held for 10 hours / 36000s -> 120x median winner)
    l1 = make_trade(tenant_id, run_id, pnl="-50.0000", opened_at=t0 + timedelta(minutes=30), closed_at=t0 + timedelta(minutes=35))
    l2 = make_trade(tenant_id, run_id, pnl="-300.0000", opened_at=t0 + timedelta(minutes=40), closed_at=t0 + timedelta(hours=10, minutes=40))

    context = AnalyticsCalculationContext(
        tenant_id=tenant_id, broker="EXNESS", account_number=10001, server_name="Exness-Real",
        reconstruction_run_id=run_id, reconciliation_run_id=None,
        data_integrity_score=Decimal("100.00"), integrity_grade="AAA", is_compromised=False,
        data_trust_status="TRUSTED", quality_warnings=(), reporting_currency="USD",
    )

    patterns = AnalyticsPatternEngine.detect_all_patterns([w1, w2, w3, l1, l2], context)
    loser_pat = [p for p in patterns if p["pattern_type"] == "POSSIBLE_LOSER_HOLDING"]
    assert len(loser_pat) == 1
    assert float(loser_pat[0]["evidence_payload"]["duration_multiplier"]) >= 3.5


@pytest.mark.asyncio
async def test_drawdown_acceleration_detector():
    """Verifies sudden equity collapse detection (drawdown acceleration)."""
    tenant_id = uuid.uuid4()
    run_id = uuid.uuid4()
    t0 = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)

    # 3 consecutive heavy losses within 1 hour totaling $1,500 on a $10,000 initial balance (15% drop)
    t1 = make_trade(tenant_id, run_id, pnl="-500.0000", opened_at=t0, closed_at=t0 + timedelta(minutes=15))
    t2 = make_trade(tenant_id, run_id, pnl="-500.0000", opened_at=t0 + timedelta(minutes=20), closed_at=t0 + timedelta(minutes=35))
    t3 = make_trade(tenant_id, run_id, pnl="-500.0000", opened_at=t0 + timedelta(minutes=40), closed_at=t0 + timedelta(minutes=55))

    context = AnalyticsCalculationContext(
        tenant_id=tenant_id, broker="EXNESS", account_number=10001, server_name="Exness-Real",
        reconstruction_run_id=run_id, reconciliation_run_id=None,
        data_integrity_score=Decimal("100.00"), integrity_grade="AAA", is_compromised=False,
        data_trust_status="TRUSTED", quality_warnings=(), reporting_currency="USD",
    )

    patterns = AnalyticsPatternEngine.detect_all_patterns([t1, t2, t3], context, initial_balance=Decimal("10000.0000"))
    dd_pat = [p for p in patterns if p["pattern_type"] == "POSSIBLE_DRAWDOWN_ACCELERATION"]
    assert len(dd_pat) == 1
    assert dd_pat[0]["severity"] == "CRITICAL"


# ==============================================================================
# 4. HISTORICAL BASELINE & DRIFT ENGINE
# ==============================================================================

@pytest.mark.asyncio
async def test_historical_baseline_drift_detection():
    """Verifies detection of material drift when recent win rate drops significantly vs baseline."""
    tenant_id = uuid.uuid4()
    run_id = uuid.uuid4()
    now = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)

    # Baseline period (days -25 to -8): 5 winning trades (100% win rate)
    base_trades = [
        make_trade(tenant_id, run_id, pnl="100.0000", opened_at=now - timedelta(days=20 - i), closed_at=now - timedelta(days=20 - i) + timedelta(hours=1))
        for i in range(5)
    ]
    # Current period (last 7 days): 4 losses, 1 win (20% win rate -> -80% drop)
    curr_trades = [
        make_trade(tenant_id, run_id, pnl="-50.0000", opened_at=now - timedelta(days=5 - i), closed_at=now - timedelta(days=5 - i) + timedelta(hours=1))
        for i in range(4)
    ]
    curr_trades.append(make_trade(tenant_id, run_id, pnl="50.0000", opened_at=now - timedelta(days=1), closed_at=now - timedelta(days=1) + timedelta(hours=1)))

    all_trades = base_trades + curr_trades

    context = AnalyticsCalculationContext(
        tenant_id=tenant_id, broker="EXNESS", account_number=10001, server_name="Exness-Real",
        reconstruction_run_id=run_id, reconciliation_run_id=None,
        data_integrity_score=Decimal("100.00"), integrity_grade="AAA", is_compromised=False,
        data_trust_status="TRUSTED", quality_warnings=(), reporting_currency="USD",
    )

    baselines = AnalyticsBaselineEngine.compute_all_baselines(all_trades, context, as_of_time=now)
    b7 = next(b for b in baselines if b["comparison_cohort"] == "CURRENT_7D_VS_PREV_30D")

    assert b7["overall_trajectory"] in ("DEGRADING", "HIGH_RISK_SHIFT")
    assert any(d["metric"] == "WIN_RATE" and d["drift_type"] == "DEGRADATION" for d in b7["detected_drifts"])


# ==============================================================================
# 5. TRADING DNA SYNTHESIS & REPLAY DETERMINISM
# ==============================================================================

@pytest.mark.asyncio
async def test_trading_dna_synthesis_and_determinism():
    """Verifies deterministic Trading DNA classification and proves Run A == Run B determinism."""
    tenant_id = uuid.uuid4()
    run_id = uuid.uuid4()
    t0 = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)

    # Scalper trades (holding duration 2 minutes)
    trades = [
        make_trade(tenant_id, run_id, symbol="EURUSD", pnl="50.0000", opened_at=t0 + timedelta(minutes=i * 10), closed_at=t0 + timedelta(minutes=i * 10 + 2))
        for i in range(10)
    ]

    context = AnalyticsCalculationContext(
        tenant_id=tenant_id, broker="EXNESS", account_number=10001, server_name="Exness-Real",
        reconstruction_run_id=run_id, reconciliation_run_id=None,
        data_integrity_score=Decimal("100.00"), integrity_grade="AAA", is_compromised=False,
        data_trust_status="TRUSTED", quality_warnings=(), reporting_currency="USD",
    )

    dna_1 = AnalyticsDNAEngine.synthesize_dna_profile(trades, [], context)
    dna_2 = AnalyticsDNAEngine.synthesize_dna_profile(trades, [], context)

    # Invariant: Style is Scalper
    assert dna_1["primary_trading_style"] == "SCALPER"
    assert dna_1["risk_appetite_grade"] == "CONSERVATIVE"
    assert "EURUSD" in dna_1["favored_instruments"]

    # Replay Determinism: Run A == Run B
    assert dna_1["radar_dimensions"] == dna_2["radar_dimensions"]
    assert dna_1["consistency_score"] == dna_2["consistency_score"]
    assert dna_1["discipline_score"] == dna_2["discipline_score"]


# ==============================================================================
# 6. INTEGRATION SERVICE & DATA INTEGRITY GATE
# ==============================================================================

@pytest.mark.asyncio
async def test_analytics_service_e2e_and_integrity_gate(db_session: AsyncSession):
    """Verifies end-to-end analytics orchestration, persistence, and Data Integrity Gate."""
    tenant_id = uuid.uuid4()
    account_num = 20001
    server_name = "Exness-Real"
    now_utc = datetime.now(timezone.utc)

    # 1. Create Sync State and Reconstruction Run
    sync = AccountSyncState(
        id=uuid.uuid4(), tenant_id=tenant_id, account_number=account_num, server_name=server_name,
        currency="USD", trade_mode="HEDGING",
    )
    db_session.add(sync)

    recon_run = ReconstructionRun(
        id=uuid.uuid4(), tenant_id=tenant_id, account_number=account_num, server_name=server_name,
        status="COMPLETED", reason="TEST_PHASE7", started_at=now_utc,
    )
    db_session.add(recon_run)
    sync.active_reconstruction_run_id = recon_run.id

    # 2. Add Compromised Reconciliation Run (Score: 82.00 Grade: C)
    reconcil_run = ReconciliationRun(
        id=uuid.uuid4(), tenant_id=tenant_id, account_number=account_num, server_name=server_name,
        reconstruction_run_id=recon_run.id, reconciliation_type="POINT_IN_TIME",
        as_of_time_msc=1000, as_of_timestamp_utc=now_utc, status="COMPLETED",
        data_integrity_score=Decimal("82.00"), integrity_grade="C", is_clean=False,
        discrepancy_count=2, critical_count=1, high_count=1, medium_count=0, low_count=0, info_count=0,
        reconciliation_engine_version="6.0.0", tolerance_profile_version="1.0.0", severity_policy_version="1.0.0",
        instrument_spec_version="1.0.0", fx_source_version="1.0.0",
    )
    db_session.add(reconcil_run)

    # 3. Add Trades
    t1 = make_trade(tenant_id, recon_run.id, account_number=account_num, pnl="150.0000", opened_at=now_utc)
    t2 = make_trade(tenant_id, recon_run.id, account_number=account_num, pnl="-50.0000", opened_at=now_utc + timedelta(hours=1))
    db_session.add_all([t1, t2])
    await db_session.flush()

    # 4. Execute Full Analytics Pipeline
    res = await AnalyticsService.compute_and_persist_analytics(
        session=db_session,
        tenant_id=tenant_id,
        account_number=account_num,
        server_name=server_name,
    )

    # 5. Verify Data Integrity Gate Flags
    assert res["is_compromised"] is True
    assert res["data_trust_status"] == "DATA_TRUST_DEGRADED"
    assert len(res["quality_warnings"]) > 0
    assert "below trust threshold" in res["quality_warnings"][0]

    # 6. Verify Database Persistence
    stmt_snap = select(AnalyticsSnapshot).where(AnalyticsSnapshot.tenant_id == tenant_id)
    res_snap = await db_session.execute(stmt_snap)
    snap = res_snap.scalar_one()
    assert snap.net_pnl == Decimal("100.0000")
    assert snap.total_trades == 2
    assert snap.is_compromised is True

    stmt_dna = select(TradingDNAProfile).where(TradingDNAProfile.tenant_id == tenant_id)
    res_dna = await db_session.execute(stmt_dna)
    dna = res_dna.scalar_one()
    assert dna.primary_trading_style is not None


# ==============================================================================
# 7. MULTI-TENANT ISOLATION
# ==============================================================================

@pytest.mark.asyncio
async def test_analytics_multi_tenant_isolation(db_session: AsyncSession):
    """Verifies that Tenant A cannot query or view Tenant B's analytics or Trading DNA."""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    account_num = 30001
    now_utc = datetime.now(timezone.utc)

    # Setup Tenant A
    run_a = ReconstructionRun(id=uuid.uuid4(), tenant_id=tenant_a, account_number=account_num, server_name="Exness-Real", status="COMPLETED", reason="RUN_A", started_at=now_utc)
    t_a = make_trade(tenant_a, run_a.id, account_number=account_num, pnl="500.0000", opened_at=now_utc)
    db_session.add_all([run_a, t_a])

    # Setup Tenant B
    run_b = ReconstructionRun(id=uuid.uuid4(), tenant_id=tenant_b, account_number=account_num, server_name="Exness-Real", status="COMPLETED", reason="RUN_B", started_at=now_utc)
    t_b = make_trade(tenant_b, run_b.id, account_number=account_num, pnl="-200.0000", opened_at=now_utc)
    db_session.add_all([run_b, t_b])
    await db_session.flush()

    # Compute for Tenant A
    res_a = await AnalyticsService.compute_and_persist_analytics(session=db_session, tenant_id=tenant_a, account_number=account_num, target_reconstruction_run_id=run_a.id)
    # Compute for Tenant B
    res_b = await AnalyticsService.compute_and_persist_analytics(session=db_session, tenant_id=tenant_b, account_number=account_num, target_reconstruction_run_id=run_b.id)

    # Assert Isolation
    stmt_a = select(AnalyticsSnapshot).where(AnalyticsSnapshot.tenant_id == tenant_a)
    snaps_a = (await db_session.execute(stmt_a)).scalars().all()
    assert len(snaps_a) == 1
    assert snaps_a[0].net_pnl == Decimal("500.0000")

    stmt_b = select(AnalyticsSnapshot).where(AnalyticsSnapshot.tenant_id == tenant_b)
    snaps_b = (await db_session.execute(stmt_b)).scalars().all()
    assert len(snaps_b) == 1
    assert snaps_b[0].net_pnl == Decimal("-200.0000")
