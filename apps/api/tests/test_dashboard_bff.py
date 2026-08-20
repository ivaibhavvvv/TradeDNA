"""TradeDNA Phase 8A - Dashboard BFF (Backend-For-Frontend) Test Suite.
Comprehensive verification of server-side logical account authorization, device hierarchy,
multi-tenant isolation, deterministic Daily Trading Brief rules, HTTP API integration,
and data provenance.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.exceptions import NotFoundException
from src.core.security import create_access_token
from src.main import app
from src.models.analytics import (
    AnalyticsSnapshot,
    BehavioralPattern,
    TradingDNAProfile,
)
from src.models.canonical_ledger import CanonicalTrade
from src.models.device import Device
from src.models.raw_event import RawAccountSnapshot, RawIngressPayload
from src.models.reconciliation import ReconciliationRun
from src.models.reconstruction_run import ReconstructionRun
from src.models.sync_state import AccountSyncState
from src.models.tenant import Tenant
from src.models.user import User
from src.services.dashboard_service import DashboardService


@pytest.mark.asyncio
async def test_dashboard_overview_default_account(db_session: AsyncSession):
    """Verifies default authorized account resolution from authenticated JWT context."""
    tenant = Tenant(id=uuid.uuid4(), name="Default Tenant")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="default@tradedna.io", password_hash="hash", full_name="Default User")
    db_session.add_all([tenant, user])

    act_num = 10001
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
        last_successful_sync_at=now_utc - timedelta(seconds=10),
    )
    db_session.add(sync)
    await db_session.flush()

    res = await DashboardService.get_dashboard_overview(session=db_session, user=user)

    assert res["has_account"] is True
    assert res["account_summary"]["account_number"] == act_num
    assert res["account_summary"]["broker"] == "EXNESS"
    assert res["account_summary"]["server_name"] == server_name


@pytest.mark.asyncio
async def test_dashboard_overview_explicit_account(db_session: AsyncSession):
    """Verifies query parameter account resolution when owned by the authenticated tenant."""
    tenant = Tenant(id=uuid.uuid4(), name="Multi-Account Tenant")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="multi@tradedna.io", password_hash="hash", full_name="Multi User")
    db_session.add_all([tenant, user])

    # Account 1
    sync1 = AccountSyncState(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=10001,
        server_name="Exness-Real1",
        currency="USD",
        trade_mode="REAL",
        sync_status="CURRENT",
    )
    # Account 2
    sync2 = AccountSyncState(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=10002,
        server_name="Exness-Real2",
        currency="EUR",
        trade_mode="REAL",
        sync_status="CURRENT",
    )
    db_session.add_all([sync1, sync2])
    await db_session.flush()

    # Query explicit account 10002
    res = await DashboardService.get_dashboard_overview(session=db_session, user=user, account_number=10002)
    assert res["has_account"] is True
    assert res["account_summary"]["account_number"] == 10002
    assert res["account_summary"]["currency"] == "EUR"


@pytest.mark.asyncio
async def test_tenant_isolation_rejection(db_session: AsyncSession):
    """Verifies that Tenant A cannot query Tenant B's account number (Returns 404, zero leakage)."""
    tenant_a = Tenant(id=uuid.uuid4(), name="Tenant A")
    user_a = User(id=uuid.uuid4(), tenant_id=tenant_a.id, email="a@tradedna.io", password_hash="hash", full_name="User A")

    tenant_b = Tenant(id=uuid.uuid4(), name="Tenant B")
    user_b = User(id=uuid.uuid4(), tenant_id=tenant_b.id, email="b@tradedna.io", password_hash="hash", full_name="User B")

    db_session.add_all([tenant_a, user_a, tenant_b, user_b])

    # Account 99001 belongs to Tenant B
    sync_b = AccountSyncState(
        id=uuid.uuid4(),
        tenant_id=tenant_b.id,
        account_number=99001,
        server_name="Exness-Real1",
        currency="USD",
        trade_mode="REAL",
        sync_status="CURRENT",
    )
    db_session.add(sync_b)
    await db_session.flush()

    # User A tries to query Account 99001 -> Expect 404 NotFound
    with pytest.raises(NotFoundException):
        await DashboardService.get_dashboard_overview(session=db_session, user=user_a, account_number=99001)


@pytest.mark.asyncio
async def test_device_hierarchy_representation(db_session: AsyncSession):
    """Verifies logical account correctly aggregates multiple physical MT5 connector devices."""
    tenant = Tenant(id=uuid.uuid4(), name="Device Tenant")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="dev@tradedna.io", password_hash="hash", full_name="Device User")
    db_session.add_all([tenant, user])

    act_num = 20001
    now_utc = datetime.now(timezone.utc)

    sync = AccountSyncState(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=act_num,
        server_name="Exness-Real",
        currency="USD",
        trade_mode="REAL",
        sync_status="CURRENT",
    )
    db_session.add(sync)

    # Physical Device 1: Desktop MT5 EA
    d1 = Device(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=act_num,
        server_name="Exness-Real",
        trade_mode="REAL",
        currency="USD",
        device_secret="s1",
        device_secret_hash="h1",
        terminal_build=4150,
        connector_version="1.0.0",
        is_active=True,
        last_seen_at=now_utc - timedelta(seconds=5),
    )
    # Physical Device 2: VPS MT5 EA
    d2 = Device(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=act_num,
        server_name="Exness-Real",
        trade_mode="REAL",
        currency="USD",
        device_secret="s2",
        device_secret_hash="h2",
        terminal_build=4180,
        connector_version="1.0.1",
        is_active=True,
        last_seen_at=now_utc - timedelta(seconds=12),
    )
    db_session.add_all([d1, d2])
    await db_session.flush()

    res = await DashboardService.get_dashboard_overview(session=db_session, user=user)

    assert len(res["connected_devices"]) == 2
    builds = {d["terminal_build"] for d in res["connected_devices"]}
    assert builds == {4150, 4180}
    assert res["sync_health"]["is_connected"] is True


@pytest.mark.asyncio
async def test_sync_trigger_authorization(db_session: AsyncSession):
    """Verifies that sync triggers are authorized for tenant owner and rejected for non-owners."""
    tenant_a = Tenant(id=uuid.uuid4(), name="Tenant A")
    user_a = User(id=uuid.uuid4(), tenant_id=tenant_a.id, email="a2@tradedna.io", password_hash="hash", full_name="User A")

    tenant_b = Tenant(id=uuid.uuid4(), name="Tenant B")
    user_b = User(id=uuid.uuid4(), tenant_id=tenant_b.id, email="b2@tradedna.io", password_hash="hash", full_name="User B")

    db_session.add_all([tenant_a, user_a, tenant_b, user_b])

    sync_a = AccountSyncState(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        account_number=30001,
        server_name="Exness-Real",
        currency="USD",
        trade_mode="REAL",
        sync_status="CURRENT",
    )
    db_session.add(sync_a)
    await db_session.flush()

    # User A triggers sync on 30001 -> Success
    res_a = await DashboardService.request_sync_trigger(session=db_session, user=user_a, account_number=30001)
    assert res_a["status"] == "SYNC_REQUESTED"
    assert res_a["account_number"] == 30001

    # User B triggers sync on 30001 -> 404 NotFound
    with pytest.raises(NotFoundException):
        await DashboardService.request_sync_trigger(session=db_session, user=user_b, account_number=30001)


@pytest.mark.asyncio
async def test_data_provenance_and_integrity_flags(db_session: AsyncSession):
    """Verifies exact data provenance timestamps and integrity score flag propagation."""
    tenant = Tenant(id=uuid.uuid4(), name="Integrity Tenant")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="integ@tradedna.io", password_hash="hash", full_name="Integ User")
    db_session.add_all([tenant, user])

    act_num = 40001
    server_name = "Exness-Real"
    now_utc = datetime.now(timezone.utc)

    recon_run = ReconstructionRun(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=act_num,
        server_name=server_name,
        status="COMPLETED",
        reason="PERIODIC",
        started_at=now_utc,
    )
    db_session.add(recon_run)

    sync = AccountSyncState(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=act_num,
        server_name=server_name,
        currency="USD",
        trade_mode="REAL",
        sync_status="CURRENT",
        active_reconstruction_run_id=recon_run.id,
        last_successful_sync_at=now_utc - timedelta(seconds=20),
    )
    db_session.add(sync)

    # Reconciliation Run with Degraded Integrity (e.g. 84.50 Score)
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
        data_integrity_score=Decimal("84.50"),
        integrity_grade="B",
        is_clean=False,
        discrepancy_count=2,
        high_count=1,
        medium_count=1,
    )
    db_session.add(recon_audit)
    await db_session.flush()

    res = await DashboardService.get_dashboard_overview(session=db_session, user=user)

    assert res["data_integrity"]["score"] == "84.50"
    assert res["data_integrity"]["grade"] == "B"
    assert res["data_integrity"]["is_compromised"] is True
    assert res["data_integrity"]["trust_status"] == "DATA_TRUST_DEGRADED"
    assert res["provenance"]["reconstruction_run_id"] == str(recon_run.id)
    assert res["provenance"]["integrity_score"] == "84.50"


@pytest.mark.asyncio
async def test_daily_trading_brief_rules(db_session: AsyncSession):
    """Verifies deterministic Daily Trading Brief rules (P&L, trades, sessions, instruments, lot comparisons)."""
    tenant = Tenant(id=uuid.uuid4(), name="Brief Tenant")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="brief@tradedna.io", password_hash="hash", full_name="Brief User")
    db_session.add_all([tenant, user])

    act_num = 50001
    server_name = "Exness-Real"
    now_utc = datetime.now(timezone.utc)

    recon_run = ReconstructionRun(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=act_num,
        server_name=server_name,
        status="COMPLETED",
        reason="INITIAL",
        started_at=now_utc,
    )
    db_session.add(recon_run)

    sync = AccountSyncState(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=act_num,
        server_name=server_name,
        currency="USD",
        trade_mode="REAL",
        sync_status="CURRENT",
        active_reconstruction_run_id=recon_run.id,
    )
    db_session.add(sync)

    # 30-Day Analytics Baseline (Avg lot size: 0.50)
    snap = AnalyticsSnapshot(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        broker="EXNESS",
        account_number=act_num,
        server_name=server_name,
        reconstruction_run_id=recon_run.id,
        period_type="30D",
        start_time_utc=now_utc - timedelta(days=30),
        end_time_utc=now_utc,
        total_trades=100,
        winning_trades=60,
        losing_trades=40,
        breakeven_trades=0,
        win_rate=Decimal("0.6000"),
        loss_rate=Decimal("0.4000"),
        gross_profit=Decimal("6000.0000"),
        gross_loss=Decimal("3000.0000"),
        net_pnl=Decimal("3000.0000"),
        profit_factor=Decimal("2.0000"),
        expectancy=Decimal("30.0000"),
        payoff_ratio=Decimal("1.3333"),
        avg_trade=Decimal("30.0000"),
        median_trade=Decimal("25.0000"),
        avg_winner=Decimal("100.0000"),
        avg_loser=Decimal("75.0000"),
        largest_winner=Decimal("400.0000"),
        largest_loser=Decimal("-250.0000"),
        max_drawdown_amount=Decimal("500.0000"),
        max_drawdown_pct=Decimal("0.0400"),
        recovery_factor=Decimal("6.0000"),
        drawdown_duration_sec=3600,
        recovery_duration_sec=7200,
        avg_holding_sec=900,
        median_holding_sec=750,
        avg_winner_holding_sec=800,
        avg_loser_holding_sec=1100,
        duration_ratio=Decimal("1.3750"),
        total_volume_lots=Decimal("50.0000"),
        avg_lot_size=Decimal("0.5000"),
        max_lot_size=Decimal("2.0000"),
        max_consecutive_wins=6,
        max_consecutive_losses=3,
        hhi_symbol_concentration=Decimal("0.5000"),
        top_symbol_volume_pct=Decimal("0.7000"),
        currency="USD",
        is_compromised=False,
        data_integrity_score=Decimal("100.00"),
        integrity_grade="AAA",
        calculation_version="7.0.0",
        metrics_json={},
    )
    db_session.add(snap)

    # Today's Trade 1: London Session EURUSD +$300.00 (1.00 Lot)
    london_time = datetime(now_utc.year, now_utc.month, now_utc.day, 9, 30, 0, tzinfo=timezone.utc)
    t1 = CanonicalTrade(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        reconstruction_run_id=recon_run.id,
        account_number=act_num,
        server_name=server_name,
        symbol="EURUSD",
        side="BUY",
        account_mode="HEDGING",
        position_ticket=5001,
        total_entry_volume=Decimal("1.0000"),
        total_exit_volume=Decimal("1.0000"),
        open_volume=Decimal("0.0000"),
        vwap_entry_price=Decimal("1.080000"),
        vwap_exit_price=Decimal("1.083000"),
        realized_gross_pnl=Decimal("300.0000"),
        total_commission=Decimal("-3.5000"),
        total_swap=Decimal("0.0000"),
        total_fees=Decimal("0.0000"),
        realized_net_pnl=Decimal("296.5000"),
        trade_status="CLOSED",
        opened_at_msc=int(london_time.timestamp() * 1000),
        opened_at_utc=london_time,
        closed_at_msc=int((london_time + timedelta(minutes=15)).timestamp() * 1000),
        closed_at_utc=london_time + timedelta(minutes=15),
    )
    db_session.add(t1)
    await db_session.flush()

    res = await DashboardService.get_dashboard_overview(session=db_session, user=user)

    brief = res["daily_trading_brief"]
    assert brief["today_trade_count"] == 1
    assert brief["today_net_pnl"] == "296.50"
    assert brief["today_win_rate"] == "1.0000"
    assert brief["strongest_session"] == "LONDON"
    assert brief["strongest_instrument"] == "EURUSD"
    assert brief["today_avg_lot_size"] == "1.00"
    assert brief["baseline_avg_lot_size"] == "0.50"


@pytest.mark.asyncio
async def test_inactive_revoked_connector(db_session: AsyncSession):
    """Verifies that revoked or inactive connector devices report is_connected=False."""
    tenant = Tenant(id=uuid.uuid4(), name="Revoked Tenant")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="rev@tradedna.io", password_hash="hash", full_name="Rev User")
    db_session.add_all([tenant, user])

    act_num = 60001
    sync = AccountSyncState(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=act_num,
        server_name="Exness-Real",
        currency="USD",
        trade_mode="REAL",
        sync_status="DISCONNECTED",
    )
    db_session.add(sync)

    # Revoked Device
    d = Device(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=act_num,
        server_name="Exness-Real",
        trade_mode="REAL",
        currency="USD",
        device_secret="s",
        device_secret_hash="h",
        terminal_build=4150,
        connector_version="1.0.0",
        is_active=False,
        is_revoked=True,
    )
    db_session.add(d)
    await db_session.flush()

    res = await DashboardService.get_dashboard_overview(session=db_session, user=user)

    assert res["sync_health"]["is_connected"] is False
    assert res["connected_devices"][0]["is_active"] is False


@pytest.mark.asyncio
async def test_missing_analytics_data_handled_gracefully(db_session: AsyncSession):
    """Verifies dashboard overview returns clean structure even when analytics snapshot is not yet synthesized."""
    tenant = Tenant(id=uuid.uuid4(), name="No Analytics Tenant")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="no_analytics@tradedna.io", password_hash="hash", full_name="No Analytics User")
    db_session.add_all([tenant, user])

    sync = AccountSyncState(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=70001,
        server_name="Exness-Real",
        currency="USD",
        trade_mode="REAL",
        sync_status="SYNCING",
    )
    db_session.add(sync)
    await db_session.flush()

    res = await DashboardService.get_dashboard_overview(session=db_session, user=user)

    assert res["has_account"] is True
    assert res["performance_summary"] is None
    assert res["risk_summary"] is None
    assert res["trading_dna"] is None
    assert res["daily_trading_brief"]["today_trade_count"] == 0


@pytest.mark.asyncio
async def test_authorized_accounts_listing(db_session: AsyncSession):
    """Verifies get_authorized_accounts lists all tenant accounts."""
    tenant = Tenant(id=uuid.uuid4(), name="Listing Tenant")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="listing@tradedna.io", password_hash="hash", full_name="Listing User")
    db_session.add_all([tenant, user])

    sync1 = AccountSyncState(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=80001,
        server_name="Exness-Real1",
        currency="USD",
        trade_mode="REAL",
        sync_status="CURRENT",
    )
    sync2 = AccountSyncState(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=80002,
        server_name="Exness-Real2",
        currency="EUR",
        trade_mode="REAL",
        sync_status="CURRENT",
    )
    db_session.add_all([sync1, sync2])
    await db_session.flush()

    accounts = await DashboardService.get_authorized_accounts(session=db_session, user=user)
    assert len(accounts) == 2
    act_nums = {a["account_number"] for a in accounts}
    assert act_nums == {80001, 80002}


@pytest.mark.asyncio
async def test_dashboard_http_endpoints_unauthenticated():
    """Verifies HTTP 401 Unauthorized on unauthenticated dashboard requests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res1 = await client.get("/api/v1/dashboard/overview")
        assert res1.status_code == 401

        res2 = await client.get("/api/v1/dashboard/accounts")
        assert res2.status_code == 401

        res3 = await client.post("/api/v1/dashboard/sync-trigger", json={"account_number": 10001})
        assert res3.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_phase8c_endpoints(db_session: AsyncSession):
    """Verifies all Phase 8C interactive intelligence endpoints with authenticated client."""
    tenant = Tenant(id=uuid.uuid4(), name="Phase8C Tenant")
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, email="phase8c@tradedna.io", password_hash="hash", full_name="Phase8C Tester")
    db_session.add_all([tenant, user])

    act_num = 99001
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
    db_session.add(sync)

    recon_run = ReconstructionRun(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=act_num,
        server_name=server_name,
        status="ACTIVE",
    )
    db_session.add(recon_run)

    trade1 = CanonicalTrade(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        reconstruction_run_id=recon_run.id,
        account_number=act_num,
        server_name=server_name,
        symbol="XAUUSD",
        side="BUY",
        account_mode="HEDGING",
        position_ticket=123456,
        total_entry_volume=Decimal("1.0000"),
        total_exit_volume=Decimal("1.0000"),
        vwap_entry_price=Decimal("2000.00"),
        vwap_exit_price=Decimal("2010.00"),
        realized_gross_pnl=Decimal("100.00"),
        total_commission=Decimal("-2.00"),
        total_swap=Decimal("0.00"),
        total_fees=Decimal("-2.00"),
        realized_net_pnl=Decimal("98.00"),
        trade_status="CLOSED",
        opened_at_msc=int(now_utc.timestamp() * 1000),
        opened_at_utc=now_utc,
        closed_at_utc=now_utc + timedelta(minutes=15),
        duration_seconds=900,
    )
    db_session.add(trade1)

    pattern1 = BehavioralPattern(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        account_number=act_num,
        server_name=server_name,
        reconstruction_run_id=recon_run.id,
        pattern_type="REVENGE_TRADING",
        detection_status="RULE_MATCHED",
        evidence_strength="STRONG",
        severity="HIGH",
        window_start_utc=now_utc - timedelta(hours=1),
        window_end_utc=now_utc,
        affected_metrics={"metric": "LOSS_RECOVERY"},
        evidence_payload={"trade_id": str(trade1.id), "ticket": 123456},
    )
    db_session.add(pattern1)

    await db_session.commit()

    token = create_access_token(subject=str(user.id), tenant_id=str(tenant.id))
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Performance endpoint
        res_perf = await client.get("/api/v1/dashboard/performance?period=ALL", headers=headers)
        assert res_perf.status_code == 200
        p_json = res_perf.json()
        assert p_json["has_data"] is True
        assert len(p_json["equity_curve"]) >= 1

        # 2. Trades list endpoint
        res_trades = await client.get("/api/v1/dashboard/trades?limit=10&offset=0", headers=headers)
        assert res_trades.status_code == 200
        t_json = res_trades.json()
        assert t_json["total_count"] == 1
        assert t_json["items"][0]["symbol"] == "XAUUSD"

        # 3. Trade detail endpoint
        res_td = await client.get(f"/api/v1/dashboard/trades/{trade1.id}", headers=headers)
        assert res_td.status_code == 200
        td_json = res_td.json()
        assert td_json["symbol"] == "XAUUSD"
        assert len(td_json["behavioral_citations"]) >= 1

        # 4. Risk endpoint
        res_risk = await client.get("/api/v1/dashboard/risk", headers=headers)
        assert res_risk.status_code == 200
        assert res_risk.json()["has_data"] is True

        # 5. Behavior endpoint
        res_beh = await client.get("/api/v1/dashboard/behavior", headers=headers)
        assert res_beh.status_code == 200
        b_json = res_beh.json()
        assert b_json["total_detected"] >= 1
        assert b_json["patterns"][0]["pattern_type"] == "REVENGE_TRADING"

        # 6. Trading DNA endpoint
        res_dna = await client.get("/api/v1/dashboard/trading-dna", headers=headers)
        assert res_dna.status_code == 200

        # 7. Instruments endpoint
        res_inst = await client.get("/api/v1/dashboard/instruments", headers=headers)
        assert res_inst.status_code == 200

        # 8. Sessions endpoint
        res_sess = await client.get("/api/v1/dashboard/sessions", headers=headers)
        assert res_sess.status_code == 200

        # 9. Calendar endpoint
        res_cal = await client.get("/api/v1/dashboard/calendar", headers=headers)
        assert res_cal.status_code == 200
        cal_json = res_cal.json()
        assert len(cal_json["days"]) >= 1

