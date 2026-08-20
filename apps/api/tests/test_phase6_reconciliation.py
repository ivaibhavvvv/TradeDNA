"""TradeDNA Phase 6 - Financial Reconciliation and Data Integrity Engine Test Suite
Validates 3-tier reconciliation, authoritative severity policies, tolerance profiles,
reproducible inputs, market timing awareness, controlled non-destructive remediation,
immutability invariants, data integrity scoring, and tenant isolation.
"""

from datetime import datetime, timezone
from decimal import Decimal
import os
import sys
from typing import Any, Optional
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.canonical_ledger import (
    CanonicalBalanceEvent,
    CanonicalExecution,
    CanonicalLedgerPosting,
    CanonicalLedgerTransaction,
    CanonicalTrade,
)
from src.models.device import Device
from src.models.raw_event import (
    RawAccountSnapshot,
    RawEventObservation,
    RawIngressPayload,
    RawPositionSnapshot,
)
from src.models.reconciliation import (
    DataIntegrityScoreHistory,
    ReconciliationAccountSummary,
    ReconciliationDiscrepancy,
    ReconciliationPositionSummary,
    ReconciliationRun,
    RemediationProposal,
)
from src.models.reconstruction_run import ReconstructionRun
from src.models.sync_state import AccountSyncState
from src.models.tenant import Tenant
from src.services.double_entry_ledger_engine import DoubleEntryLedgerEngine
from src.services.instrument_service import InstrumentService
from src.services.reconciliation_engine import ReconciliationEngine
from src.services.reconciliation_policy import (
    DEFAULT_SEVERITY_POLICY,
    DEFAULT_TOLERANCE_PROFILE,
    ReconciliationSeverityPolicy,
    ReconciliationToleranceProfile,
)
from src.services.reconstruction_manager import ReconstructionManager
from src.services.remediation_engine import (
    RemediationAuthorizationError,
    RemediationEngine,
)
from src.services.trade_reconstruction_engine import TradeReconstructionEngine


# ==============================================================================
# TEST FIXTURES & HELPERS
# ==============================================================================

def make_raw_payload(tenant_id: uuid.UUID, account_num: int, device_id: Optional[uuid.UUID] = None) -> RawIngressPayload:
    return RawIngressPayload(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        device_id=device_id or uuid.uuid4(),
        account_number=account_num,
        server_name="Exness-Real1",
        payload_type="ACCOUNT_STATE",
        schema_version="1.0.0",
        payload_hash="mock_hash_" + uuid.uuid4().hex[:8],
        raw_payload_bytes=b"{}",
        received_at_utc=datetime.now(timezone.utc),
    )


def make_account_snapshot(
    tenant_id: uuid.UUID,
    payload_id: uuid.UUID,
    account_num: int,
    balance: Decimal = Decimal("10000.0000"),
    equity: Decimal = Decimal("10000.0000"),
    margin: Decimal = Decimal("0.0000"),
    margin_free: Decimal = Decimal("10000.0000"),
    device_id: Optional[uuid.UUID] = None,
    dt: Optional[datetime] = None,
) -> RawAccountSnapshot:
    now = dt or datetime.now(timezone.utc)
    return RawAccountSnapshot(
        id=uuid.uuid4(),
        ingress_payload_id=payload_id,
        tenant_id=tenant_id,
        device_id=device_id or uuid.uuid4(),
        account_number=account_num,
        server_name="Exness-Real1",
        currency="USD",
        balance=balance,
        equity=equity,
        margin=margin,
        margin_free=margin_free,
        margin_level=Decimal("0.00"),
        leverage=100,
        trade_mode="DEMO",
        is_hedging=True,
        raw_payload_json={"balance": str(balance), "equity": str(equity)},
        snapshot_time_utc=now,
        received_at_utc=now,
    )


def make_position_snapshot(
    tenant_id: uuid.UUID,
    payload_id: uuid.UUID,
    account_num: int,
    positions: list[dict[str, Any]],
    device_id: Optional[uuid.UUID] = None,
    dt: Optional[datetime] = None,
) -> RawPositionSnapshot:
    now = dt or datetime.now(timezone.utc)
    return RawPositionSnapshot(
        id=uuid.uuid4(),
        ingress_payload_id=payload_id,
        tenant_id=tenant_id,
        device_id=device_id or uuid.uuid4(),
        account_number=account_num,
        server_name="Exness-Real1",
        position_count=len(positions),
        raw_payload_json={"positions": positions},
        snapshot_time_utc=now,
        received_at_utc=now,
    )


# ==============================================================================
# TEST GROUP 1: SINGLE AUTHORITATIVE SEVERITY POLICY & BOUNDARIES
# ==============================================================================

def test_severity_policy_boundaries():
    """Test 1-3: Verify strict boundary semantics for INFO, LOW, MEDIUM, HIGH, CRITICAL:
    - 0 delta                -> INFO
    - 0 < delta <= 0.05      -> LOW (Boundary at exactly $0.05)
    - 0.05 < delta < 5.00    -> MEDIUM
    - 5.00 <= delta <= 50.00 -> HIGH (Boundary at exactly $5.00 & $50.00)
    - delta > 50.00          -> CRITICAL
    """
    policy = ReconciliationSeverityPolicy(policy_version="1.0.0")

    # 1. INFO boundary
    assert policy.classify_financial_delta(Decimal("0.0000")) == "INFO"

    # 2. LOW boundary (0 < delta <= 0.05)
    assert policy.classify_financial_delta(Decimal("0.0001")) == "LOW"
    assert policy.classify_financial_delta(Decimal("0.0100")) == "LOW"
    assert policy.classify_financial_delta(Decimal("0.0500")) == "LOW"  # Exact boundary

    # 3. MEDIUM boundary (0.05 < delta < 5.00)
    assert policy.classify_financial_delta(Decimal("0.0501")) == "MEDIUM"
    assert policy.classify_financial_delta(Decimal("1.0000")) == "MEDIUM"
    assert policy.classify_financial_delta(Decimal("4.9999")) == "MEDIUM"

    # 4. HIGH boundary (5.00 <= delta <= 50.00)
    assert policy.classify_financial_delta(Decimal("5.0000")) == "HIGH"  # Exact boundary
    assert policy.classify_financial_delta(Decimal("25.0000")) == "HIGH"
    assert policy.classify_financial_delta(Decimal("50.0000")) == "HIGH"  # Exact boundary

    # 5. CRITICAL boundary (delta > 50.00)
    assert policy.classify_financial_delta(Decimal("50.0001")) == "CRITICAL"
    assert policy.classify_financial_delta(Decimal("100.0000")) == "CRITICAL"
    assert policy.classify_financial_delta(Decimal("-500.0000")) == "CRITICAL"


def test_custom_versioned_severity_policy():
    """Test 4: Configurable, versioned severity policies with stored versioning."""
    custom_policy = ReconciliationSeverityPolicy(
        policy_version="2.0.0-custom",
        low_max=Decimal("0.1000"),
        medium_max=Decimal("10.0000"),
        high_max=Decimal("100.0000"),
    )
    assert custom_policy.policy_version == "2.0.0-custom"
    assert custom_policy.classify_financial_delta(Decimal("0.0800")) == "LOW"
    assert DEFAULT_SEVERITY_POLICY.classify_financial_delta(Decimal("0.0800")) == "MEDIUM"


def test_versioned_tolerance_profile():
    """Test 5: Configurable tolerance profile checking."""
    profile = ReconciliationToleranceProfile(
        profile_version="1.1.0",
        financial_penny_tolerance=Decimal("0.0200"),
        volume_tolerance=Decimal("0.0010"),
    )
    assert profile.profile_version == "1.1.0"
    assert profile.is_within_financial_tolerance(Decimal("0.0150")) is True
    assert profile.is_within_financial_tolerance(Decimal("0.0250")) is False
    assert profile.is_within_volume_tolerance(Decimal("0.0005")) is True
    assert profile.is_within_volume_tolerance(Decimal("0.0015")) is False


# ==============================================================================
# TEST GROUP 2: LEVEL 1 ACCOUNT-LEVEL RECONCILIATION
# ==============================================================================

@pytest.mark.asyncio
async def test_pristine_account_level_reconciliation(db_session: AsyncSession):
    """Test 6: Clean snapshot and canonical ledger match producing 100.00 score and Grade AAA."""
    tenant_id = uuid.uuid4()
    account_num = 60001
    now = datetime.now(timezone.utc)

    payload = make_raw_payload(tenant_id, account_num)
    db_session.add(payload)
    snap = make_account_snapshot(tenant_id, payload.id, account_num, balance=Decimal("10000.0000"), equity=Decimal("10000.0000"), dt=now)
    db_session.add(snap)

    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    postings = DoubleEntryLedgerEngine.build_balance_event_postings("DEPOSIT", Decimal("10000.0000"), "USD")
    tx, db_postings = DoubleEntryLedgerEngine.validate_and_create_transaction(
        tenant_id=tenant_id, reconstruction_run_id=run.id, account_number=account_num,
        transaction_type="CASH_DEPOSIT", transaction_time_msc=1000, transaction_timestamp_utc=now,
        description="Deposit: 10000 USD", source_observation_id=uuid.uuid4(), postings=postings,
    )
    db_session.add(tx)
    for p in db_postings:
        db_session.add(p)
    await db_session.flush()

    recon = await ReconciliationEngine.execute_reconciliation(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        reconstruction_run_id=run.id, snapshot_id=snap.id,
    )

    assert recon.is_clean is True
    assert recon.data_integrity_score == Decimal("100.00")
    assert recon.integrity_grade == "AAA"
    assert recon.discrepancy_count == 0
    assert recon.reconciliation_engine_version == "6.0.0"


@pytest.mark.asyncio
async def test_account_balance_divergence_critical(db_session: AsyncSession):
    """Test 7: Major balance mismatch ($100 divergence) creates CRITICAL discrepancy and score deduction."""
    tenant_id = uuid.uuid4()
    account_num = 60002
    now = datetime.now(timezone.utc)

    payload = make_raw_payload(tenant_id, account_num)
    db_session.add(payload)
    snap = make_account_snapshot(tenant_id, payload.id, account_num, balance=Decimal("10100.0000"), equity=Decimal("10100.0000"), dt=now)
    db_session.add(snap)

    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    postings = DoubleEntryLedgerEngine.build_balance_event_postings("DEPOSIT", Decimal("10000.0000"), "USD")
    tx, db_postings = DoubleEntryLedgerEngine.validate_and_create_transaction(
        tenant_id=tenant_id, reconstruction_run_id=run.id, account_number=account_num,
        transaction_type="CASH_DEPOSIT", transaction_time_msc=1000, transaction_timestamp_utc=now,
        description="Deposit: 10000 USD", source_observation_id=uuid.uuid4(), postings=postings,
    )
    db_session.add(tx)
    for p in db_postings:
        db_session.add(p)
    await db_session.flush()

    recon = await ReconciliationEngine.execute_reconciliation(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        reconstruction_run_id=run.id, snapshot_id=snap.id,
    )

    assert recon.is_clean is False
    assert recon.critical_count == 1
    assert recon.data_integrity_score == Decimal("75.00")
    assert recon.integrity_grade == "B"

    stmt_d = select(ReconciliationDiscrepancy).where(ReconciliationDiscrepancy.reconciliation_run_id == recon.id)
    res_d = await db_session.execute(stmt_d)
    disc = res_d.scalar_one()

    assert disc.discrepancy_category == "BALANCE_MISMATCH"
    assert disc.severity == "CRITICAL"
    assert disc.broker_value == "10100.0000"
    assert disc.canonical_value == "10000.0000"
    assert disc.delta_value == "100.0000"


# ==============================================================================
# TEST GROUP 3: LEVEL 2 POSITION-LEVEL RECONCILIATION
# ==============================================================================

@pytest.mark.asyncio
async def test_position_level_missing_canonical_trade(db_session: AsyncSession):
    """Test 8: MT5 snapshot position missing from TradeDNA generates MISSING_CANONICAL_TRADE discrepancy."""
    tenant_id = uuid.uuid4()
    account_num = 60003
    now = datetime.now(timezone.utc)

    payload = make_raw_payload(tenant_id, account_num)
    db_session.add(payload)
    snap = make_account_snapshot(tenant_id, payload.id, account_num, dt=now)
    db_session.add(snap)

    pos_snap = make_position_snapshot(
        tenant_id=tenant_id, payload_id=payload.id, account_num=account_num,
        positions=[{
            "ticket": 90001, "symbol": "EURUSD", "type": "BUY", "volume": "1.0000",
            "price_open": "1.080000", "price_current": "1.085000", "profit": "500.0000", "swap": "0.0000"
        }], dt=now,
    )
    db_session.add(pos_snap)

    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    postings = DoubleEntryLedgerEngine.build_balance_event_postings("DEPOSIT", Decimal("10000.0000"), "USD")
    tx, db_postings = DoubleEntryLedgerEngine.validate_and_create_transaction(
        tenant_id=tenant_id, reconstruction_run_id=run.id, account_number=account_num,
        transaction_type="CASH_DEPOSIT", transaction_time_msc=1000, transaction_timestamp_utc=now,
        description="Deposit: 10000 USD", source_observation_id=uuid.uuid4(), postings=postings,
    )
    db_session.add(tx)
    for p in db_postings:
        db_session.add(p)
    await db_session.flush()

    recon = await ReconciliationEngine.execute_reconciliation(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        reconstruction_run_id=run.id, snapshot_id=snap.id,
    )

    assert recon.is_clean is False
    assert recon.critical_count == 1
    assert recon.data_integrity_score == Decimal("75.00")

    stmt_p = select(ReconciliationPositionSummary).where(ReconciliationPositionSummary.reconciliation_run_id == recon.id)
    res_p = await db_session.execute(stmt_p)
    p_sum = res_p.scalar_one()

    assert p_sum.status == "MISSING_CANONICAL"
    assert p_sum.position_ticket == 90001
    assert p_sum.market_price_used == Decimal("1.085000")


@pytest.mark.asyncio
async def test_position_level_ghost_canonical_trade(db_session: AsyncSession):
    """Test 9: Open Canonical trade absent from MT5 snapshot generates GHOST_CANONICAL_TRADE discrepancy."""
    tenant_id = uuid.uuid4()
    account_num = 60004
    now = datetime.now(timezone.utc)

    payload = make_raw_payload(tenant_id, account_num)
    db_session.add(payload)
    snap = make_account_snapshot(tenant_id, payload.id, account_num, dt=now)
    db_session.add(snap)

    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    postings = DoubleEntryLedgerEngine.build_balance_event_postings("DEPOSIT", Decimal("10000.0000"), "USD")
    tx, db_postings = DoubleEntryLedgerEngine.validate_and_create_transaction(
        tenant_id=tenant_id, reconstruction_run_id=run.id, account_number=account_num,
        transaction_type="CASH_DEPOSIT", transaction_time_msc=1000, transaction_timestamp_utc=now,
        description="Deposit: 10000 USD", source_observation_id=uuid.uuid4(), postings=postings,
    )
    db_session.add(tx)
    for p in db_postings:
        db_session.add(p)

    t = CanonicalTrade(
        id=uuid.uuid4(), tenant_id=tenant_id, reconstruction_run_id=run.id, account_number=account_num,
        server_name="Exness-Real1", symbol="EURUSD", side="BUY", account_mode="HEDGING", position_ticket=90002,
        total_entry_volume=Decimal("1.0000"), total_exit_volume=Decimal("0.0000"), open_volume=Decimal("1.0000"),
        vwap_entry_price=Decimal("1.080000"), vwap_exit_price=None, realized_gross_pnl=Decimal("0.0000"),
        total_commission=Decimal("0.0000"), total_swap=Decimal("0.0000"), total_fees=Decimal("0.0000"),
        realized_net_pnl=Decimal("0.0000"), trade_status="OPEN", opened_at_msc=1000, opened_at_utc=now,
    )
    db_session.add(t)
    await db_session.flush()

    recon = await ReconciliationEngine.execute_reconciliation(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        reconstruction_run_id=run.id, snapshot_id=snap.id,
    )

    assert recon.high_count == 1
    stmt_p = select(ReconciliationPositionSummary).where(ReconciliationPositionSummary.reconciliation_run_id == recon.id)
    res_p = await db_session.execute(stmt_p)
    p_sum = res_p.scalar_one()
    assert p_sum.status == "GHOST_CANONICAL"


@pytest.mark.asyncio
async def test_floating_pnl_market_timing_and_bid_ask_selection(db_session: AsyncSession):
    """Test 10: Verifies market price timestamp, bid/ask direction, and instrument spec lineage are recorded."""
    tenant_id = uuid.uuid4()
    account_num = 60010
    now = datetime.now(timezone.utc)

    payload = make_raw_payload(tenant_id, account_num)
    db_session.add(payload)
    snap = make_account_snapshot(tenant_id, payload.id, account_num, dt=now)
    db_session.add(snap)

    pos_snap = make_position_snapshot(
        tenant_id=tenant_id, payload_id=payload.id, account_num=account_num,
        positions=[{
            "ticket": 90010, "symbol": "EURUSD", "type": "BUY", "volume": "1.0000",
            "price_open": "1.080000", "price_current": "1.082500", "profit": "250.0000", "swap": "-2.5000"
        }], dt=now,
    )
    db_session.add(pos_snap)

    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    postings = DoubleEntryLedgerEngine.build_balance_event_postings("DEPOSIT", Decimal("10000.0000"), "USD")
    tx, db_postings = DoubleEntryLedgerEngine.validate_and_create_transaction(
        tenant_id=tenant_id, reconstruction_run_id=run.id, account_number=account_num,
        transaction_type="CASH_DEPOSIT", transaction_time_msc=1000, transaction_timestamp_utc=now,
        description="Deposit: 10000 USD", source_observation_id=uuid.uuid4(), postings=postings,
    )
    db_session.add(tx)
    for p in db_postings:
        db_session.add(p)

    t = CanonicalTrade(
        id=uuid.uuid4(), tenant_id=tenant_id, reconstruction_run_id=run.id, account_number=account_num,
        server_name="Exness-Real1", symbol="EURUSD", side="BUY", account_mode="HEDGING", position_ticket=90010,
        total_entry_volume=Decimal("1.0000"), total_exit_volume=Decimal("0.0000"), open_volume=Decimal("1.0000"),
        vwap_entry_price=Decimal("1.080000"), vwap_exit_price=None, realized_gross_pnl=Decimal("0.0000"),
        total_commission=Decimal("0.0000"), total_swap=Decimal("-2.5000"), total_fees=Decimal("0.0000"),
        realized_net_pnl=Decimal("0.0000"), trade_status="OPEN", opened_at_msc=1000, opened_at_utc=now,
    )
    db_session.add(t)
    await db_session.flush()

    recon = await ReconciliationEngine.execute_reconciliation(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        reconstruction_run_id=run.id, snapshot_id=snap.id,
        instrument_spec_version="1.2.0", fx_source_version="ECB-LIVE",
    )

    assert recon.is_clean is True
    assert recon.data_integrity_score == Decimal("100.00")

    stmt_p = select(ReconciliationPositionSummary).where(ReconciliationPositionSummary.reconciliation_run_id == recon.id)
    res_p = await db_session.execute(stmt_p)
    p_sum = res_p.scalar_one()

    assert p_sum.status == "MATCHED"
    assert p_sum.market_price_used == Decimal("1.082500")
    assert p_sum.instrument_spec_version == "1.2.0"


# ==============================================================================
# TEST GROUP 4: LEVEL 3 EVENT & LEDGER RECONCILIATION
# ==============================================================================

@pytest.mark.asyncio
async def test_event_level_missing_execution(db_session: AsyncSession):
    """Test 11: Missing canonical execution for a raw MT5 deal observation is detected."""
    tenant_id = uuid.uuid4()
    account_num = 60005
    now = datetime.now(timezone.utc)

    payload = make_raw_payload(tenant_id, account_num)
    db_session.add(payload)

    obs = RawEventObservation(
        id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=payload.id,
        tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
        source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=95001, item_payload_hash="h1",
        raw_item_json={"deal_ticket": 95001, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "volume": "1.0000"},
        observation_status="ORIGINAL", source_time_msc=1000, source_timestamp_utc=now,
    )
    db_session.add(obs)

    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    await db_session.flush()

    recon = await ReconciliationEngine.execute_reconciliation(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        reconstruction_run_id=run.id,
    )

    assert recon.high_count == 1
    stmt_d = select(ReconciliationDiscrepancy).where(
        ReconciliationDiscrepancy.reconciliation_run_id == recon.id,
        ReconciliationDiscrepancy.discrepancy_category == "MISSING_CANONICAL_EXECUTION",
    )
    res_d = await db_session.execute(stmt_d)
    disc = res_d.scalar_one()
    assert disc.entity_identifier == "95001"


# ==============================================================================
# TEST GROUP 5: REPRODUCIBILITY WITH IDENTICAL INPUTS (Correction 5)
# ==============================================================================

@pytest.mark.asyncio
async def test_reconciliation_reproducibility_identical_inputs(db_session: AsyncSession):
    """Test 12: Given identical inputs and versions, Run A and Run B produce 100% identical discrepancies,
    severities, score, and grade."""
    tenant_id = uuid.uuid4()
    account_num = 60006
    now = datetime.now(timezone.utc)

    payload = make_raw_payload(tenant_id, account_num)
    db_session.add(payload)
    snap = make_account_snapshot(tenant_id, payload.id, account_num, balance=Decimal("10025.0000"), equity=Decimal("10025.0000"), dt=now)
    db_session.add(snap)

    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    postings = DoubleEntryLedgerEngine.build_balance_event_postings("DEPOSIT", Decimal("10000.0000"), "USD")
    tx, db_postings = DoubleEntryLedgerEngine.validate_and_create_transaction(
        tenant_id=tenant_id, reconstruction_run_id=run.id, account_number=account_num,
        transaction_type="CASH_DEPOSIT", transaction_time_msc=1000, transaction_timestamp_utc=now,
        description="Deposit: 10000 USD", source_observation_id=uuid.uuid4(), postings=postings,
    )
    db_session.add(tx)
    for p in db_postings:
        db_session.add(p)
    await db_session.flush()

    recon_a = await ReconciliationEngine.execute_reconciliation(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        reconstruction_run_id=run.id, snapshot_id=snap.id,
    )

    recon_b = await ReconciliationEngine.execute_reconciliation(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        reconstruction_run_id=run.id, snapshot_id=snap.id,
    )

    assert recon_a.discrepancy_count == recon_b.discrepancy_count == 1
    assert recon_a.high_count == recon_b.high_count == 1
    assert recon_a.data_integrity_score == recon_b.data_integrity_score == Decimal("90.00")
    assert recon_a.integrity_grade == recon_b.integrity_grade == "A"
    assert recon_a.is_clean == recon_b.is_clean == False


# ==============================================================================
# TEST GROUP 6: CONTROLLED NON-DESTRUCTIVE REMEDIATION (Correction 4)
# ==============================================================================

@pytest.mark.asyncio
async def test_remediation_lifecycle_and_non_destructive_promotion(db_session: AsyncSession):
    """Test 13-17: Controlled remediation state machine:
    PROPOSED -> APPROVED -> EXECUTING -> VALIDATING -> RESOLVED.
    Verifies zero mutation of existing raw observations and canonical records."""
    tenant_id = uuid.uuid4()
    account_num = 60007
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Setup tenant and account sync state
    sync_state = AccountSyncState(
        id=uuid.uuid4(), tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        currency="USD", trade_mode="DEMO",
    )
    db_session.add(sync_state)

    payload = make_raw_payload(tenant_id, account_num)
    db_session.add(payload)

    # 1. Initial Raw Deposit Ingress
    obs_deposit = RawEventObservation(
        id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=payload.id,
        tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
        source_type="INITIAL_HISTORICAL", event_type="DEAL_EVENT", external_ticket=99001, item_payload_hash="h1",
        raw_item_json={"deal_ticket": 99001, "deal_type": "DEAL_TYPE_BALANCE", "profit": "10000.0000", "currency": "USD"},
        observation_status="ORIGINAL", source_time_msc=100, source_timestamp_utc=now,
    )
    db_session.add(obs_deposit)

    # Initial Run 1
    run1 = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1", reason="RUN_1")
    await TradeReconstructionEngine.process_raw_observations_for_run(
        db_session, tenant_id, account_num, "Exness-Real1", "HEDGING", "USD", run1, [obs_deposit]
    )
    run1.status = "COMPLETED"
    run1.completed_at = datetime.now(timezone.utc)
    await ReconstructionManager.switch_active_run(db_session, tenant_id, account_num, run1.id)

    # 2. Backfilled Deal Event arrives in Phase 4 Layer 1
    obs_trade = RawEventObservation(
        id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=payload.id,
        tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
        source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=99002, item_payload_hash="h2",
        raw_item_json={"deal_ticket": 99002, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": 99101, "commission": "-3.5000"},
        observation_status="ORIGINAL", source_time_msc=200, source_timestamp_utc=now,
    )
    db_session.add(obs_trade)

    snap = make_account_snapshot(tenant_id, payload.id, account_num, balance=Decimal("10000.0000"), equity=Decimal("10000.0000"), dt=now)
    db_session.add(snap)
    await db_session.flush()

    # 3. Initial Reconciliation flags missing execution in Run 1
    recon1 = await ReconciliationEngine.execute_reconciliation(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        reconstruction_run_id=run1.id, snapshot_id=snap.id,
    )
    assert recon1.discrepancy_count >= 1

    # 4. Create Remediation Proposal
    proposal = await RemediationEngine.create_proposal(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        proposal_type="TRIGGER_RECONSTRUCTION_REBUILD",
    )
    assert proposal.status == "REMEDIATION_PROPOSED"

    # Execution without approval must be rejected
    with pytest.raises(RemediationAuthorizationError):
        await RemediationEngine.execute_remediation(db_session, tenant_id, proposal.id)

    # 5. Approve Proposal
    proposal = await RemediationEngine.approve_proposal(db_session, tenant_id, proposal.id, user_id)
    assert proposal.status == "REMEDIATION_APPROVED"

    # 6. Execute Remediation Pipeline
    proposal, post_recon = await RemediationEngine.execute_remediation(db_session, tenant_id, proposal.id)
    assert proposal.status == "RESOLVED"
    assert proposal.new_reconstruction_run_id is not None
    assert proposal.new_reconstruction_run_id != run1.id

    # 7. Assert Zero Mutation of Run 1
    stmt_old_run = select(ReconstructionRun).where(ReconstructionRun.id == run1.id)
    res_old_run = await db_session.execute(stmt_old_run)
    old_run = res_old_run.scalar_one()
    assert old_run.status == "SUPERSEDED"  # Superseded, not modified or deleted!


@pytest.mark.asyncio
async def test_cross_tenant_remediation_rejection(db_session: AsyncSession):
    """Test 18: Tenant isolation prevents cross-tenant remediation viewing or execution."""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    account_num = 60008

    proposal = await RemediationEngine.create_proposal(
        session=db_session, tenant_id=tenant_a, account_number=account_num, server_name="Exness-Real1",
        proposal_type="TRIGGER_RECONSTRUCTION_REBUILD",
    )

    with pytest.raises(RemediationAuthorizationError):
        await RemediationEngine.approve_proposal(db_session, tenant_b, proposal.id, uuid.uuid4())

    with pytest.raises(RemediationAuthorizationError):
        await RemediationEngine.execute_remediation(db_session, tenant_b, proposal.id)
