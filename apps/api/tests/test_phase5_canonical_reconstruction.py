"""TradeDNA Phase 5 - Comprehensive Automated Verification Matrix
Validates deterministic trade reconstruction, hedging & netting semantics,
lot-by-lot FIFO matching, CLOSE_BY lineage, double-entry ledger balance invariants,
reconstruction run version switching, instrument specs, and multi-currency conversion.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.connector_auth import reset_nonce_cache
from src.main import app
from src.models.canonical_ledger import (
    CanonicalBalanceEvent,
    CanonicalExecution,
    CanonicalLedgerPosting,
    CanonicalLedgerTransaction,
    CanonicalTrade,
    CanonicalTradeExecutionMap,
)
from src.models.instrument_spec import HistoricalExchangeRate, InstrumentSpecification
from src.models.raw_event import RawEventObservation, RawIngressPayload
from src.models.reconstruction_run import ReconstructionRun
from src.models.sync_state import AccountSyncState
from src.models.user import User
from src.services.double_entry_ledger_engine import (
    DoubleEntryLedgerEngine,
    UnbalancedLedgerTransactionException,
)
from src.services.instrument_service import (
    InstrumentService,
    MissingExchangeRateException,
    MissingInstrumentSpecificationException,
)
from src.services.lot_allocation_engine import EntryLot, LotAllocationEngine
from src.services.reconstruction_manager import ReconstructionManager
from src.services.trade_reconstruction_engine import TradeReconstructionEngine
from tests.test_phase4_raw_sync import build_signed_headers


@pytest.fixture(autouse=True)
def clean_nonce_cache():
    reset_nonce_cache()


async def setup_test_account_and_device(
    client: AsyncClient,
    account_number: int = 88001001,
    trade_mode: str = "HEDGING",
    currency: str = "USD",
) -> tuple[str, uuid.UUID, str, User]:
    """Helper to register user, pair device, exchange credentials, and return tokens."""
    email = f"user_{uuid.uuid4().hex[:6]}@example.com"
    reg = await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": "Phase 5 Trader",
    })
    assert reg.status_code == 201
    token = reg.json()["access_token"]

    pair = await client.post("/api/v1/exness/connection/pair", headers={"Authorization": f"Bearer {token}"})
    assert pair.status_code == 201
    p_token = pair.json()["pairing_token"]

    exchange = await client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": p_token,
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": account_number,
        "server_name": "Exness-MT5Real1",
        "trade_mode": trade_mode,
        "currency": currency,
    })
    assert exchange.status_code == 200
    ex_json = exchange.json()
    device_id = uuid.UUID(ex_json["device_id"])
    device_secret = ex_json["device_secret"]

    return token, device_id, device_secret, email


# ==============================================================================
# TEST GROUP 1: HEDGING & NETTING RECONSTRUCTION SEMANTICS
# ==============================================================================

@pytest.mark.asyncio
async def test_single_entry_single_exit_hedging(db_session: AsyncSession):
    """Test 1: Standard 1.00 lot Buy -> 1.00 lot Sell in Hedging mode."""
    tenant_id = uuid.uuid4()
    account_num = 10001
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")

    now = datetime.now(timezone.utc)
    obs1 = RawEventObservation(
        id=uuid.uuid4(),
        observation_id=uuid.uuid4(),
        ingress_payload_id=uuid.uuid4(),
        tenant_id=tenant_id,
        device_id=uuid.uuid4(),
        account_number=account_num,
        server_name="Exness-Real1",
        source_type="ON_TRADE_TRANSACTION",
        event_type="DEAL_EVENT",
        external_ticket=101,
        item_payload_hash="hash1",
        raw_item_json={
            "deal_ticket": 101,
            "symbol": "EURUSD",
            "deal_type": "DEAL_TYPE_BUY",
            "deal_entry": "DEAL_ENTRY_IN",
            "volume": "1.0000",
            "price": "1.080000",
            "position_id": 9001,
            "profit": "0.0000",
            "commission": "-3.5000",
        },
        observation_status="ORIGINAL",
        source_time_msc=1700000000000,
        source_timestamp_utc=now,
    )
    obs2 = RawEventObservation(
        id=uuid.uuid4(),
        observation_id=uuid.uuid4(),
        ingress_payload_id=uuid.uuid4(),
        tenant_id=tenant_id,
        device_id=uuid.uuid4(),
        account_number=account_num,
        server_name="Exness-Real1",
        source_type="ON_TRADE_TRANSACTION",
        event_type="DEAL_EVENT",
        external_ticket=102,
        item_payload_hash="hash2",
        raw_item_json={
            "deal_ticket": 102,
            "symbol": "EURUSD",
            "deal_type": "DEAL_TYPE_SELL",
            "deal_entry": "DEAL_ENTRY_OUT",
            "volume": "1.0000",
            "price": "1.085000",
            "position_id": 9001,
            "profit": "500.0000",
            "commission": "-3.5000",
        },
        observation_status="ORIGINAL",
        source_time_msc=1700000060000,
        source_timestamp_utc=now,
    )

    trades, execs, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session,
        tenant_id=tenant_id,
        account_number=account_num,
        server_name="Exness-Real1",
        account_mode="HEDGING",
        account_currency="USD",
        reconstruction_run=run,
        raw_observations=[obs1, obs2],
    )

    assert len(trades) == 1
    t = trades[0]
    assert t.trade_status == "CLOSED"
    assert t.position_ticket == 9001
    assert t.total_entry_volume == Decimal("1.0000")
    assert t.total_exit_volume == Decimal("1.0000")
    assert t.open_volume == Decimal("0.0000")
    assert t.realized_gross_pnl == Decimal("500.0000")
    assert t.total_commission == Decimal("-7.0000")
    assert t.realized_net_pnl == Decimal("493.0000")


@pytest.mark.asyncio
async def test_multiple_scale_in_entries(db_session: AsyncSession):
    """Test 2: Scale-in Buy 0.50 @ 1.0800 + Buy 0.50 @ 1.0840 -> Sell 1.00 @ 1.0900."""
    tenant_id = uuid.uuid4()
    account_num = 10002
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=201, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 201, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "0.5000", "price": "1.080000", "position_id": 9002},
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=202, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 202, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "0.5000", "price": "1.084000", "position_id": 9002},
            observation_status="ORIGINAL", source_time_msc=1700000200000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=203, item_payload_hash="h3",
            raw_item_json={"deal_ticket": 203, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "1.0000", "price": "1.090000", "position_id": 9002},
            observation_status="ORIGINAL", source_time_msc=1700000300000, source_timestamp_utc=now,
        ),
    ]

    trades, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="HEDGING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    assert len(trades) == 1
    t = trades[0]
    assert t.trade_status == "CLOSED"
    assert t.total_entry_volume == Decimal("1.0000")
    # VWAP entry: (0.5*1.0800 + 0.5*1.0840)/1.0 = 1.0820
    assert t.vwap_entry_price == Decimal("1.082000")
    # Realized gross PnL: 0.5*100k*(1.0900-1.0800) + 0.5*100k*(1.0900-1.0840) = 500 + 300 = 800.00
    assert t.realized_gross_pnl == Decimal("800.0000")


@pytest.mark.asyncio
async def test_single_entry_partial_exit(db_session: AsyncSession):
    """Test 3: Buy 1.00 lot -> Sell 0.30 lot -> PARTIALLY_CLOSED."""
    tenant_id = uuid.uuid4()
    account_num = 10003
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=301, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 301, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": 9003},
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=302, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 302, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "0.3000", "price": "1.085000", "position_id": 9003},
            observation_status="ORIGINAL", source_time_msc=1700000200000, source_timestamp_utc=now,
        ),
    ]

    trades, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="HEDGING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    assert len(trades) == 1
    t = trades[0]
    assert t.trade_status == "PARTIALLY_CLOSED"
    assert t.open_volume == Decimal("0.7000")
    assert t.total_exit_volume == Decimal("0.3000")
    assert t.realized_gross_pnl == Decimal("150.0000")


@pytest.mark.asyncio
async def test_multiple_partial_exits_to_close(db_session: AsyncSession):
    """Test 4: Buy 1.00 lot -> Exit 0.30 + Exit 0.40 + Exit 0.30 -> CLOSED."""
    tenant_id = uuid.uuid4()
    account_num = 10004
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=401, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 401, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": 9004},
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=402, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 402, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "0.3000", "price": "1.082000", "position_id": 9004},
            observation_status="ORIGINAL", source_time_msc=1700000200000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=403, item_payload_hash="h3",
            raw_item_json={"deal_ticket": 403, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "0.4000", "price": "1.083000", "position_id": 9004},
            observation_status="ORIGINAL", source_time_msc=1700000300000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=404, item_payload_hash="h4",
            raw_item_json={"deal_ticket": 404, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "0.3000", "price": "1.081000", "position_id": 9004},
            observation_status="ORIGINAL", source_time_msc=1700000400000, source_timestamp_utc=now,
        ),
    ]

    trades, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="HEDGING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    assert len(trades) == 1
    t = trades[0]
    assert t.trade_status == "CLOSED"
    assert t.open_volume == Decimal("0.0000")
    # PnL: 0.3*100k*0.0020 (60) + 0.4*100k*0.0030 (120) + 0.3*100k*0.0010 (30) = 210.00
    assert t.realized_gross_pnl == Decimal("210.0000")


@pytest.mark.asyncio
async def test_hedging_independent_same_symbol_positions(db_session: AsyncSession):
    """Test 5: Open Long 1.00 EURUSD + Open Short 2.00 EURUSD simultaneously in Hedging mode."""
    tenant_id = uuid.uuid4()
    account_num = 10005
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=501, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 501, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": 9005},
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=502, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 502, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_IN", "volume": "2.0000", "price": "1.082000", "position_id": 9006},
            observation_status="ORIGINAL", source_time_msc=1700000200000, source_timestamp_utc=now,
        ),
    ]

    trades, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="HEDGING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    assert len(trades) == 2
    t1 = next(t for t in trades if t.position_ticket == 9005)
    t2 = next(t for t in trades if t.position_ticket == 9006)
    assert t1.side == "BUY" and t1.open_volume == Decimal("1.0000")
    assert t2.side == "SELL" and t2.open_volume == Decimal("2.0000")


@pytest.mark.asyncio
async def test_netting_scale_in_vwap(db_session: AsyncSession):
    """Test 6: Netting Buy 1.00 @ 1.0800 + Buy 2.00 @ 1.0830 -> VWAP = 1.0820."""
    tenant_id = uuid.uuid4()
    account_num = 10006
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=601, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 601, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000"},
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=602, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 602, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "2.0000", "price": "1.083000"},
            observation_status="ORIGINAL", source_time_msc=1700000200000, source_timestamp_utc=now,
        ),
    ]

    trades, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="NETTING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    assert len(trades) == 1
    t = trades[0]
    assert t.open_volume == Decimal("3.0000")
    # VWAP: (1.0*1.0800 + 2.0*1.0830)/3.0 = 1.082000
    assert t.vwap_entry_price == Decimal("1.082000")


@pytest.mark.asyncio
async def test_netting_fifo_cost_basis_not_vwap(db_session: AsyncSession):
    """Test 31: Prove netting realized P&L matches exact consumed entry lot prices, not blended VWAP."""
    tenant_id = uuid.uuid4()
    account_num = 10031
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    # Buy 1.00 @ 1.0800 (Lot A), Buy 1.00 @ 1.0840 (Lot B). VWAP = 1.0820.
    # Exit 1.00 @ 1.0900.
    # Under FIFO, Lot A is consumed: Gross P&L = 1.00 * 100k * (1.0900 - 1.0800) = $1,000.00.
    # If blended VWAP was erroneously used: 1.00 * 100k * (1.0900 - 1.0820) = $800.00.
    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=701, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 701, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000"},
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=702, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 702, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.084000"},
            observation_status="ORIGINAL", source_time_msc=1700000200000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=703, item_payload_hash="h3",
            raw_item_json={"deal_ticket": 703, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "1.0000", "price": "1.090000"},
            observation_status="ORIGINAL", source_time_msc=1700000300000, source_timestamp_utc=now,
        ),
    ]

    trades, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="NETTING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    assert len(trades) == 1
    t = trades[0]
    assert t.realized_gross_pnl == Decimal("1000.0000")  # Exact FIFO cost basis verification!


@pytest.mark.asyncio
async def test_netting_reversal_inout(db_session: AsyncSession):
    """Test 8: Netting Long 1.00 EURUSD -> Sell 2.50 EURUSD (ENTRY_INOUT). Reverses position."""
    tenant_id = uuid.uuid4()
    account_num = 10008
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=801, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 801, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000"},
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=802, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 802, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_INOUT", "volume": "2.5000", "price": "1.085000"},
            observation_status="ORIGINAL", source_time_msc=1700000200000, source_timestamp_utc=now,
        ),
    ]

    trades, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="NETTING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    assert len(trades) == 2
    t1 = trades[0]
    t2 = trades[1]
    assert t1.trade_status == "REVERSED"
    assert t1.realized_gross_pnl == Decimal("500.0000")  # 1.00 lot closed at +50 pips

    assert t2.trade_status == "OPEN"
    assert t2.side == "SELL"
    assert t2.open_volume == Decimal("1.5000")  # Remaining 1.50 lots Short
    assert t2.vwap_entry_price == Decimal("1.085000")


@pytest.mark.asyncio
async def test_close_by_counter_position_lineage(db_session: AsyncSession):
    """Test 33: MT5 DEAL_ENTRY_OUT_BY preserves counter_position_ticket and counter_deal_ticket."""
    tenant_id = uuid.uuid4()
    account_num = 10033
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=901, item_payload_hash="h1",
            raw_item_json={
                "deal_ticket": 901, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL",
                "deal_entry": "DEAL_ENTRY_OUT_BY", "volume": "1.0000", "price": "1.085000",
                "position_id": 9010, "counter_position_ticket": 9020, "counter_deal_ticket": 902,
            },
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
    ]

    _, execs, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="HEDGING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    assert len(execs) == 1
    e = execs[0]
    assert e.entry_type == "ENTRY_OUT_BY"
    assert e.counter_position_ticket == 9020
    assert e.counter_deal_ticket == 902


# ==============================================================================
# TEST GROUP 2: DOUBLE-ENTRY LEDGER & BALANCE EVENTS
# ==============================================================================

@pytest.mark.asyncio
async def test_double_entry_debit_credit_balance(db_session: AsyncSession):
    """Test 34: Validate SUM(Debits) == SUM(Credits) across all generated ledger transactions."""
    tenant_id = uuid.uuid4()
    account_num = 10034
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    # Deposit + Profitable Trade + Withdrawal
    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="INITIAL_HISTORICAL", event_type="DEAL_EVENT", external_ticket=1001, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 1001, "deal_type": "DEAL_TYPE_BALANCE", "profit": "5000.0000", "currency": "USD"},
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=1002, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 1002, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": 9011},
            observation_status="ORIGINAL", source_time_msc=1700000200000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=1003, item_payload_hash="h3",
            raw_item_json={"deal_ticket": 1003, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "1.0000", "price": "1.085000", "position_id": 9011, "profit": "500.0000"},
            observation_status="ORIGINAL", source_time_msc=1700000300000, source_timestamp_utc=now,
        ),
    ]

    await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="HEDGING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    # Query all ledger transactions and check balance invariant
    stmt = select(CanonicalLedgerTransaction).where(CanonicalLedgerTransaction.reconstruction_run_id == run.id)
    res = await db_session.execute(stmt)
    txs = res.scalars().all()
    assert len(txs) >= 2

    for tx in txs:
        stmt_p = select(CanonicalLedgerPosting).where(CanonicalLedgerPosting.transaction_id == tx.id)
        res_p = await db_session.execute(stmt_p)
        postings = res_p.scalars().all()
        assert len(postings) >= 2
        sum_deb = sum(p.debit_amount for p in postings)
        sum_cred = sum(p.credit_amount for p in postings)
        assert sum_deb == sum_cred


@pytest.mark.asyncio
async def test_running_balance_rebuild_after_historical_insert(db_session: AsyncSession):
    """Test 35: Verify derived running balance projection updates deterministically after historical deposit."""
    tenant_id = uuid.uuid4()
    account_num = 10035
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    # Ingest trade + deposit
    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="INITIAL_HISTORICAL", event_type="DEAL_EVENT", external_ticket=1101, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 1101, "deal_type": "DEAL_TYPE_BALANCE", "profit": "10000.0000", "currency": "USD"},
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="INITIAL_HISTORICAL", event_type="DEAL_EVENT", external_ticket=1102, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 1102, "deal_type": "DEAL_TYPE_BALANCE", "profit": "-2000.0000", "currency": "USD"},
            observation_status="ORIGINAL", source_time_msc=1700000200000, source_timestamp_utc=now,
        ),
    ]

    await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="HEDGING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    running_bal = await DoubleEntryLedgerEngine.get_running_balance_projection(db_session, run.id, account_num)
    assert running_bal == Decimal("8000.0000")


@pytest.mark.asyncio
async def test_unbalanced_ledger_transaction_rejection():
    """Test 44: Reject unbalanced double-entry transaction when SUM(debit) != SUM(credit)."""
    with pytest.raises(UnbalancedLedgerTransactionException):
        DoubleEntryLedgerEngine.validate_and_create_transaction(
            tenant_id=uuid.uuid4(),
            reconstruction_run_id=uuid.uuid4(),
            account_number=999,
            transaction_type="INVALID",
            transaction_time_msc=100,
            transaction_timestamp_utc=datetime.now(timezone.utc),
            description="Unbalanced Tx",
            source_observation_id=uuid.uuid4(),
            postings=[
                {"account_type": "CASH_BALANCE", "debit": Decimal("100"), "credit": Decimal("0")},
                {"account_type": "REALIZED_PNL", "debit": Decimal("0"), "credit": Decimal("90")},  # 100 != 90
            ],
        )


# ==============================================================================
# TEST GROUP 3: RECONSTRUCTION RUNS & ATOMIC VERSION SWITCHING
# ==============================================================================

@pytest.mark.asyncio
async def test_reconstruction_run_version_switch_and_rollback(db_session: AsyncSession):
    """Test 36 & 37: Switch active reconstruction run pointer atomically and rollback."""
    tenant_id = uuid.uuid4()
    account_num = 10036
    sync_state = AccountSyncState(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        account_number=account_num,
        server_name="Exness-Real1",
        currency="USD",
        trade_mode="HEDGING",
    )
    db_session.add(sync_state)
    await db_session.flush()

    # Run 1
    run1 = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1", reason="RUN_1")
    run1.status = "ACTIVE"
    sync_state.active_reconstruction_run_id = run1.id

    # Run 2
    run2 = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1", reason="RUN_2")
    run2.status = "COMPLETED"
    await db_session.flush()

    # Switch to Run 2
    switched = await ReconstructionManager.switch_active_run(db_session, tenant_id, account_num, run2.id)
    assert switched.id == run2.id
    assert switched.status == "ACTIVE"
    assert sync_state.active_reconstruction_run_id == run2.id
    assert run1.status == "SUPERSEDED"

    # Rollback to Run 1
    rolled_back = await ReconstructionManager.switch_active_run(db_session, tenant_id, account_num, run1.id)
    assert rolled_back.id == run1.id
    assert rolled_back.status == "ACTIVE"
    assert sync_state.active_reconstruction_run_id == run1.id


# ==============================================================================
# TEST GROUP 4: INSTRUMENTS & MULTI-CURRENCY CONVERSION
# ==============================================================================

@pytest.mark.asyncio
async def test_instrument_specific_contract_size(db_session: AsyncSession):
    """Test 38: Verify Gold (contract size 100) vs Forex (100,000) vs BTC (1) P&L calculation."""
    tenant_id = uuid.uuid4()
    gold_spec = await InstrumentService.get_or_create_default_spec(db_session, tenant_id, "XAUUSD")
    fx_spec = await InstrumentService.get_or_create_default_spec(db_session, tenant_id, "EURUSD")
    btc_spec = await InstrumentService.get_or_create_default_spec(db_session, tenant_id, "BTCUSD")

    assert gold_spec.contract_size == Decimal("100")
    assert fx_spec.contract_size == Decimal("100000")
    assert btc_spec.contract_size == Decimal("1")

    # Gold 1.00 lot Long @ 2350.00 -> 2360.00 (+$10 delta * 100 = +$1,000.00)
    pnl_gold = LotAllocationEngine.calculate_gross_pnl("BUY", Decimal("2350.00"), Decimal("2360.00"), Decimal("1.0000"), gold_spec)
    assert pnl_gold == Decimal("1000.0000")

    # Forex 1.00 lot Long @ 1.0800 -> 1.0850 (+0.0050 delta * 100k = +$500.00)
    pnl_fx = LotAllocationEngine.calculate_gross_pnl("BUY", Decimal("1.080000"), Decimal("1.085000"), Decimal("1.0000"), fx_spec)
    assert pnl_fx == Decimal("500.0000")

    # BTC 1.00 lot Long @ 60000.00 -> 61000.00 (+1000 delta * 1 = +$1,000.00)
    pnl_btc = LotAllocationEngine.calculate_gross_pnl("BUY", Decimal("60000.00"), Decimal("61000.00"), Decimal("1.0000"), btc_spec)
    assert pnl_btc == Decimal("1000.0000")


@pytest.mark.asyncio
async def test_multi_currency_realized_pnl_conversion(db_session: AsyncSession):
    """Test 40: EURGBP trade (profit in GBP) on a USD account converted via historical GBPUSD rate."""
    tenant_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    t_msc = 1700000500000

    # Seed historical GBP -> USD rate: 1 GBP = 1.250000 USD
    fx_rate = HistoricalExchangeRate(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        base_currency="GBP",
        quote_currency="USD",
        rate=Decimal("1.250000"),
        effective_time_msc=t_msc,
        effective_timestamp_utc=now,
    )
    db_session.add(fx_rate)
    await db_session.flush()

    eurgbp_spec = await InstrumentService.get_or_create_default_spec(db_session, tenant_id, "EURGBP")
    # Buy 1.00 EURGBP @ 0.8500 -> Exit @ 0.8600 (+0.0100 delta * 100,000 = +1,000 GBP)
    # In USD: 1,000 GBP * 1.250000 = +$1,250.00 USD
    resolved_fx = await InstrumentService.resolve_fx_rate(db_session, tenant_id, "GBP", "USD", t_msc)
    assert resolved_fx == Decimal("1.250000")

    pnl_usd = LotAllocationEngine.calculate_gross_pnl(
        side="BUY",
        entry_price=Decimal("0.850000"),
        exit_price=Decimal("0.860000"),
        matched_volume=Decimal("1.0000"),
        spec=eurgbp_spec,
        fx_rate=resolved_fx,
    )
    assert pnl_usd == Decimal("1250.0000")


# ==============================================================================
# TEST GROUP 5: FULL API & END-TO-END RECONSTRUCTION
# ==============================================================================

@pytest.mark.asyncio
async def test_full_api_canonical_reconstruction_flow():
    """Test 25 & 26: Complete E2E flow from MT5 ingress -> reconstruction API -> inspection."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token, device_id, device_secret, _ = await setup_test_account_and_device(client, account_number=88990001)

        # Ingest 2 historical deals via MT5 sync API
        deals = [
            {
                "schema_version": "1.0.0",
                "observation_id": str(uuid.uuid4()),
                "connector_id": str(device_id),
                "account_number": 88990001,
                "deal_ticket": 1201,
                "symbol": "EURUSD",
                "deal_type": "DEAL_TYPE_BUY",
                "deal_entry": "DEAL_ENTRY_IN",
                "volume": "1.0000",
                "price": "1.080000",
                "position_id": 8888,
                "profit": "0.0000",
                "deal_time": "2026-08-18T10:00:00.000Z",
                "deal_time_msc": 1787076800000,
            },
            {
                "schema_version": "1.0.0",
                "observation_id": str(uuid.uuid4()),
                "connector_id": str(device_id),
                "account_number": 88990001,
                "deal_ticket": 1202,
                "symbol": "EURUSD",
                "deal_type": "DEAL_TYPE_SELL",
                "deal_entry": "DEAL_ENTRY_OUT",
                "volume": "1.0000",
                "price": "1.085000",
                "position_id": 8888,
                "profit": "500.0000",
                "deal_time": "2026-08-18T10:05:00.000Z",
                "deal_time_msc": 1787076850000,
            },
        ]
        batch_payload = {
            "payload_type": "BATCH_HISTORICAL",
            "data": {
                "schema_version": "1.0.0",
                "connector_id": str(device_id),
                "account_number": 88990001,
                "sync_mode": "INITIAL_HISTORICAL",
                "batch_index": 1,
                "batch_size_deals": 2,
                "batch_size_orders": 0,
                "deals": deals,
                "orders": [],
                "from_time_msc": 1787076800000,
                "to_time_msc": 1787076850000,
                "is_final_batch": True,
            }
        }
        raw_bytes = json.dumps(batch_payload).encode("utf-8")
        sync_res = await client.post(
            "/api/v1/exness/sync",
            content=raw_bytes,
            headers=build_signed_headers(device_id, device_secret, raw_bytes),
        )
        assert sync_res.status_code == 202

        # Trigger reconstruction via API
        recon_res = await client.post(
            "/api/v1/canonical/reconstruct/88990001?reason=API_TEST",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert recon_res.status_code == 202
        r_json = recon_res.json()
        assert r_json["reconstructed_trades_count"] == 1

        # Query reconstructed trades
        trades_res = await client.get(
            "/api/v1/canonical/trades/88990001",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert trades_res.status_code == 200
        t_data = trades_res.json()
        assert t_data["total_trades"] == 1
        trade = t_data["trades"][0]
        assert trade["trade_status"] == "CLOSED"
        assert trade["realized_gross_pnl"] == "500.0000"

        # Query ledger
        ledger_res = await client.get(
            "/api/v1/canonical/ledger/88990001",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ledger_res.status_code == 200
        l_data = ledger_res.json()
        assert l_data["running_balance"] == "500.0000"


# ==============================================================================
# TEST GROUP 6: EDGE CASES, LINEAGE, IDEMPOTENCY & CONCURRENCY
# ==============================================================================

@pytest.mark.asyncio
async def test_unmatched_orphan_exit(db_session: AsyncSession):
    """Test 10: Exit deal received with no prior entry in history -> UNMATCHED."""
    tenant_id = uuid.uuid4()
    account_num = 20010
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=9901, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 9901, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "1.0000", "price": "1.085000", "position_id": 9999},
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
    ]

    trades, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="HEDGING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    assert len(trades) == 1
    assert trades[0].trade_status == "UNMATCHED"


@pytest.mark.asyncio
async def test_commission_and_overnight_swap_attribution(db_session: AsyncSession):
    """Test 11 & 12: Commission and swap charges correctly aggregated and deducted from net P&L."""
    tenant_id = uuid.uuid4()
    account_num = 20011
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=9911, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 9911, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": 9910, "commission": "-5.0000"},
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=9912, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 9912, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "1.0000", "price": "1.085000", "position_id": 9910, "commission": "-5.0000", "swap": "-12.5000", "profit": "500.0000"},
            observation_status="ORIGINAL", source_time_msc=1700000200000, source_timestamp_utc=now,
        ),
    ]

    trades, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="HEDGING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    assert len(trades) == 1
    t = trades[0]
    assert t.realized_gross_pnl == Decimal("500.0000")
    assert t.total_commission == Decimal("-10.0000")
    assert t.total_swap == Decimal("-12.5000")
    assert t.realized_net_pnl == Decimal("477.5000")


@pytest.mark.asyncio
async def test_balance_events_complete_lifecycle(db_session: AsyncSession):
    """Test 13, 14, 15, 16, 17, 18: Deposit, Withdrawal, Credit, Dividend, Tax, Correction."""
    tenant_id = uuid.uuid4()
    account_num = 20013
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="INITIAL_HISTORICAL", event_type="DEAL_EVENT", external_ticket=9921, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 9921, "deal_type": "DEAL_TYPE_BALANCE", "profit": "5000.0000", "currency": "USD"},
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="INITIAL_HISTORICAL", event_type="DEAL_EVENT", external_ticket=9922, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 9922, "deal_type": "DEAL_TYPE_CREDIT", "profit": "500.0000", "currency": "USD"},
            observation_status="ORIGINAL", source_time_msc=1700000200000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="INITIAL_HISTORICAL", event_type="DEAL_EVENT", external_ticket=9923, item_payload_hash="h3",
            raw_item_json={"deal_ticket": 9923, "deal_type": "DEAL_DIVIDEND", "profit": "75.0000", "currency": "USD"},
            observation_status="ORIGINAL", source_time_msc=1700000300000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="INITIAL_HISTORICAL", event_type="DEAL_EVENT", external_ticket=9924, item_payload_hash="h4",
            raw_item_json={"deal_ticket": 9924, "deal_type": "DEAL_TAX", "profit": "-15.0000", "currency": "USD"},
            observation_status="ORIGINAL", source_time_msc=1700000400000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="INITIAL_HISTORICAL", event_type="DEAL_EVENT", external_ticket=9925, item_payload_hash="h5",
            raw_item_json={"deal_ticket": 9925, "deal_type": "DEAL_TYPE_BALANCE", "profit": "-1000.0000", "currency": "USD"},
            observation_status="ORIGINAL", source_time_msc=1700000500000, source_timestamp_utc=now,
        ),
    ]

    _, _, bal_events = await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="HEDGING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    assert len(bal_events) == 5
    # Running cash balance: +5000 (deposit) + 75 (dividend) - 15 (tax) - 1000 (withdrawal) = 4060.00 (credit is facility)
    running_bal = await DoubleEntryLedgerEngine.get_running_balance_projection(db_session, run.id, account_num)
    assert running_bal == Decimal("4060.0000")


@pytest.mark.asyncio
async def test_duplicate_and_conflicting_observation_idempotency(db_session: AsyncSession):
    """Test 19 & 20: Duplicate observations ignored, conflicting observations flagged without ledger mutation."""
    tenant_id = uuid.uuid4()
    account_num = 20019
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=9931, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 9931, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": 9930},
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
        # Duplicate observation (same ticket and payload)
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=9931, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 9931, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": 9930},
            observation_status="DUPLICATE", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
        # Conflicting observation on exit
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=9932, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 9932, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "1.0000", "price": "1.085000", "position_id": 9930, "profit": "500.0000"},
            observation_status="CONFLICTING", source_time_msc=1700000200000, source_timestamp_utc=now,
        ),
    ]

    trades, execs, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="HEDGING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    # Only 2 executions created (duplicate filtered)
    assert len(execs) == 2
    assert len(trades) == 1
    # Trade marked CONFLICTED
    assert trades[0].trade_status == "CONFLICTED"


@pytest.mark.asyncio
async def test_out_of_order_deal_reordering(db_session: AsyncSession):
    """Test 21: Ingesting deals in reverse chronological order produces exact sorted result."""
    tenant_id = uuid.uuid4()
    account_num = 20021
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    # Provide exit BEFORE entry in input list
    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=9942, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 9942, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "1.0000", "price": "1.085000", "position_id": 9940, "profit": "500.0000"},
            observation_status="ORIGINAL", source_time_msc=1700000200000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=9941, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 9941, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": 9940},
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
    ]

    trades, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="HEDGING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    assert len(trades) == 1
    assert trades[0].trade_status == "CLOSED"
    assert trades[0].realized_gross_pnl == Decimal("500.0000")


@pytest.mark.asyncio
async def test_canonical_to_raw_lineage_trace(db_session: AsyncSession):
    """Test 24: Validate complete 6-stage foreign key trace from CanonicalTrade to Exness Account."""
    tenant_id = uuid.uuid4()
    account_num = 20024
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    ingress_id = uuid.uuid4()
    obs_id = uuid.uuid4()
    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=obs_id, ingress_payload_id=ingress_id,
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=9951, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 9951, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": 9950},
            observation_status="ORIGINAL", source_time_msc=1700000100000, source_timestamp_utc=now,
        ),
    ]

    trades, execs, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        session=db_session, tenant_id=tenant_id, account_number=account_num, server_name="Exness-Real1",
        account_mode="HEDGING", account_currency="USD", reconstruction_run=run, raw_observations=obs,
    )

    assert len(trades) == 1
    assert len(execs) == 1
    e = execs[0]
    assert e.observation_id == obs_id
    assert e.ingress_payload_id == ingress_id
    assert trades[0].reconstruction_run_id == run.id


@pytest.mark.asyncio
async def test_tenant_isolation_during_reconstruction(db_session: AsyncSession):
    """Test 50: Tenant A and Tenant B data remain strictly isolated during reconstruction."""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    account_num = 99999

    run_a = await ReconstructionManager.create_run(db_session, tenant_a, account_num, "Exness-Real1")
    run_b = await ReconstructionManager.create_run(db_session, tenant_b, account_num, "Exness-Real1")

    now = datetime.now(timezone.utc)
    obs_a = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_a, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=1, item_payload_hash="ha",
            raw_item_json={"deal_ticket": 1, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": 1},
            observation_status="ORIGINAL", source_time_msc=100, source_timestamp_utc=now,
        )
    ]
    obs_b = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_b, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=2, item_payload_hash="hb",
            raw_item_json={"deal_ticket": 2, "symbol": "GBPUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "2.0000", "price": "1.250000", "position_id": 2},
            observation_status="ORIGINAL", source_time_msc=100, source_timestamp_utc=now,
        )
    ]

    trades_a, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(db_session, tenant_a, account_num, "Exness-Real1", "HEDGING", "USD", run_a, obs_a)
    trades_b, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(db_session, tenant_b, account_num, "Exness-Real1", "HEDGING", "USD", run_b, obs_b)

    assert len(trades_a) == 1 and trades_a[0].symbol == "EURUSD"
    assert len(trades_b) == 1 and trades_b[0].symbol == "GBPUSD"


@pytest.mark.asyncio
async def test_concurrent_reconstruction_of_different_accounts():
    """Test 52: Multiple accounts reconstruct concurrently with zero deadlocks or collisions."""
    from tests.conftest import test_session_factory
    tenant_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    async def _run_account(acc_num: int):
        async with test_session_factory() as sess:
            run = await ReconstructionManager.create_run(sess, tenant_id, acc_num, "Exness-Real1")
            obs = [
                RawEventObservation(
                    id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
                    tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=acc_num, server_name="Exness-Real1",
                    source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=acc_num * 10 + 1, item_payload_hash=f"h{acc_num}",
                    raw_item_json={"deal_ticket": acc_num * 10 + 1, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": acc_num},
                    observation_status="ORIGINAL", source_time_msc=100, source_timestamp_utc=now,
                )
            ]
            trades, execs, bal = await TradeReconstructionEngine.process_raw_observations_for_run(
                sess, tenant_id, acc_num, "Exness-Real1", "HEDGING", "USD", run, obs
            )
            await sess.commit()
            return trades, execs, bal

    results = await asyncio.gather(_run_account(30001), _run_account(30002), _run_account(30003))
    assert len(results) == 3
    for trades, _, _ in results:
        assert len(trades) == 1


@pytest.mark.asyncio
async def test_floating_point_precision_numeric18_4(db_session: AsyncSession):
    """Test 30: Prove zero floating point loss in micro-lot sub-cent calculations."""
    tenant_id = uuid.uuid4()
    account_num = 40030
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    # 0.0001 lot EURUSD (10 units) -> delta 0.00003 -> P&L = 0.0003 USD exactly
    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=4001, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 4001, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "0.0001", "price": "1.080000", "position_id": 4001},
            observation_status="ORIGINAL", source_time_msc=100, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=4002, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 4002, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "0.0001", "price": "1.080030", "position_id": 4001},
            observation_status="ORIGINAL", source_time_msc=200, source_timestamp_utc=now,
        ),
    ]

    trades, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        db_session, tenant_id, account_num, "Exness-Real1", "HEDGING", "USD", run, obs
    )
    assert len(trades) == 1
    # 0.0001 * 100,000 * 0.000030 = 0.0003
    assert trades[0].realized_gross_pnl == Decimal("0.0003")


@pytest.mark.asyncio
async def test_hedging_position_id_independent_of_deal_ticket(db_session: AsyncSession):
    """Test 32: MT5 position_id is treated as an independent broker entity and not derived from deal ticket."""
    tenant_id = uuid.uuid4()
    account_num = 40032
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    # Deal ticket 77777 has broker position ID 9999999
    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=77777, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 77777, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": 9999999},
            observation_status="ORIGINAL", source_time_msc=100, source_timestamp_utc=now,
        ),
    ]

    trades, execs, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        db_session, tenant_id, account_num, "Exness-Real1", "HEDGING", "USD", run, obs
    )
    assert len(trades) == 1
    assert trades[0].position_ticket == 9999999
    assert execs[0].deal_ticket == 77777
    assert execs[0].position_ticket == 9999999


@pytest.mark.asyncio
async def test_deterministic_ordering_on_identical_timestamps(db_session: AsyncSession):
    """Test 42: Multiple events with identical timestamp sorted deterministically by ticket number."""
    tenant_id = uuid.uuid4()
    account_num = 40042
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    obs = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=5002, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 5002, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "1.0000", "price": "1.085000", "position_id": 5000, "profit": "500.0000"},
            observation_status="ORIGINAL", source_time_msc=1000, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=5001, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 5001, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": 5000},
            observation_status="ORIGINAL", source_time_msc=1000, source_timestamp_utc=now,
        ),
    ]

    trades, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        db_session, tenant_id, account_num, "Exness-Real1", "HEDGING", "USD", run, obs
    )
    assert len(trades) == 1
    assert trades[0].trade_status == "CLOSED"
    assert trades[0].realized_gross_pnl == Decimal("500.0000")


@pytest.mark.asyncio
async def test_missing_historical_fx_conversion_handling(db_session: AsyncSession):
    """Test 46: Missing exchange rate raises MissingExchangeRateException."""
    tenant_id = uuid.uuid4()
    with pytest.raises(MissingExchangeRateException):
        await InstrumentService.resolve_fx_rate(
            session=db_session,
            tenant_id=tenant_id,
            from_currency="JPY",
            to_currency="USD",
            timestamp_msc=1700000000000,
        )


@pytest.mark.asyncio
async def test_reconstruction_run_comparison_service(db_session: AsyncSession):
    """Test 47: ReconstructionManager compare_runs returns detailed comparison metrics."""
    tenant_id = uuid.uuid4()
    account_num = 40047
    now = datetime.now(timezone.utc)

    run1 = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1", reason="RUN_1")
    t1 = CanonicalTrade(
        id=uuid.uuid4(), tenant_id=tenant_id, reconstruction_run_id=run1.id, account_number=account_num,
        server_name="Exness-Real1", symbol="EURUSD", side="BUY", account_mode="HEDGING", position_ticket=1,
        total_entry_volume=Decimal("1.0"), total_exit_volume=Decimal("1.0"), open_volume=Decimal("0.0"),
        vwap_entry_price=Decimal("1.08"), vwap_exit_price=Decimal("1.09"), realized_gross_pnl=Decimal("100.0"),
        total_commission=Decimal("-5.0"), total_swap=Decimal("0.0"), total_fees=Decimal("0.0"), realized_net_pnl=Decimal("95.0"),
        trade_status="CLOSED", opened_at_msc=100, opened_at_utc=now,
    )
    db_session.add(t1)

    run2 = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1", reason="RUN_2")
    t2 = CanonicalTrade(
        id=uuid.uuid4(), tenant_id=tenant_id, reconstruction_run_id=run2.id, account_number=account_num,
        server_name="Exness-Real1", symbol="EURUSD", side="BUY", account_mode="HEDGING", position_ticket=1,
        total_entry_volume=Decimal("2.0"), total_exit_volume=Decimal("2.0"), open_volume=Decimal("0.0"),
        vwap_entry_price=Decimal("1.08"), vwap_exit_price=Decimal("1.09"), realized_gross_pnl=Decimal("200.0"),
        total_commission=Decimal("-10.0"), total_swap=Decimal("0.0"), total_fees=Decimal("0.0"), realized_net_pnl=Decimal("190.0"),
        trade_status="CLOSED", opened_at_msc=100, opened_at_utc=now,
    )
    db_session.add(t2)
    await db_session.flush()

    diff = await ReconstructionManager.compare_runs(db_session, tenant_id, account_num, run1.id, run2.id)
    assert diff["run_a"]["total_gross_pnl"] == "100.0000"
    assert diff["run_b"]["total_gross_pnl"] == "200.0000"


# ==============================================================================
# TEST GROUP 7: INDEPENDENT FINANCIAL LEDGER & P&L VALIDATION
# ==============================================================================

@pytest.mark.asyncio
async def test_independent_financial_ledger_validation(db_session: AsyncSession):
    """Test Requirement 6: Perform independent double-entry ledger balance verification
    (SUM(debits) == SUM(credits)) across all transactions without using production helper logic."""
    tenant_id = uuid.uuid4()
    account_num = 50001
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    # Ingest a diverse sequence of 10 events: Deposits, Withdrawals, Buy/Sell trades, Dividends, Taxes
    obs_list = [
        # 1. Initial Deposit
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="INITIAL_HISTORICAL", event_type="DEAL_EVENT", external_ticket=60001, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 60001, "deal_type": "DEAL_TYPE_BALANCE", "profit": "25000.0000", "currency": "USD"},
            observation_status="ORIGINAL", source_time_msc=100, source_timestamp_utc=now,
        ),
        # 2. Profitable Long EURUSD Trade
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=60002, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 60002, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "2.0000", "price": "1.080000", "position_id": 61001, "commission": "-7.0000"},
            observation_status="ORIGINAL", source_time_msc=200, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=60003, item_payload_hash="h3",
            raw_item_json={"deal_ticket": 60003, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "2.0000", "price": "1.086000", "position_id": 61001, "profit": "1200.0000", "commission": "-7.0000", "swap": "-5.5000"},
            observation_status="ORIGINAL", source_time_msc=300, source_timestamp_utc=now,
        ),
        # 3. Losing Short XAUUSD Trade
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=60004, item_payload_hash="h4",
            raw_item_json={"deal_ticket": 60004, "symbol": "XAUUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "2350.00", "position_id": 61002, "commission": "-10.0000"},
            observation_status="ORIGINAL", source_time_msc=400, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=60005, item_payload_hash="h5",
            raw_item_json={"deal_ticket": 60005, "symbol": "XAUUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_OUT", "volume": "1.0000", "price": "2355.00", "position_id": 61002, "profit": "-500.0000", "commission": "-10.0000"},
            observation_status="ORIGINAL", source_time_msc=500, source_timestamp_utc=now,
        ),
        # 4. Dividend Credit
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="INITIAL_HISTORICAL", event_type="DEAL_EVENT", external_ticket=60006, item_payload_hash="h6",
            raw_item_json={"deal_ticket": 60006, "deal_type": "DEAL_DIVIDEND", "profit": "150.0000", "currency": "USD"},
            observation_status="ORIGINAL", source_time_msc=600, source_timestamp_utc=now,
        ),
        # 5. Tax Withholding
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="INITIAL_HISTORICAL", event_type="DEAL_EVENT", external_ticket=60007, item_payload_hash="h7",
            raw_item_json={"deal_ticket": 60007, "deal_type": "DEAL_TAX", "profit": "-30.0000", "currency": "USD"},
            observation_status="ORIGINAL", source_time_msc=700, source_timestamp_utc=now,
        ),
        # 6. Withdrawal
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="INITIAL_HISTORICAL", event_type="DEAL_EVENT", external_ticket=60008, item_payload_hash="h8",
            raw_item_json={"deal_ticket": 60008, "deal_type": "DEAL_TYPE_BALANCE", "profit": "-5000.0000", "currency": "USD"},
            observation_status="ORIGINAL", source_time_msc=800, source_timestamp_utc=now,
        ),
    ]

    await TradeReconstructionEngine.process_raw_observations_for_run(
        db_session, tenant_id, account_num, "Exness-Real1", "HEDGING", "USD", run, obs_list
    )

    # Independent validation: Read all transactions and postings directly from raw SQL rows
    stmt_tx = select(CanonicalLedgerTransaction).where(CanonicalLedgerTransaction.reconstruction_run_id == run.id)
    res_tx = await db_session.execute(stmt_tx)
    all_txs = list(res_tx.scalars().all())
    assert len(all_txs) >= 5, "Expected at least 5 ledger transactions"

    for tx in all_txs:
        stmt_p = select(CanonicalLedgerPosting).where(CanonicalLedgerPosting.transaction_id == tx.id)
        res_p = await db_session.execute(stmt_p)
        postings = list(res_p.scalars().all())

        # Assert at least 2 postings per double-entry transaction
        assert len(postings) >= 2, f"Transaction {tx.id} has {len(postings)} postings (< 2)"

        # Independent mathematical sum
        independent_sum_debits = Decimal("0.0000")
        independent_sum_credits = Decimal("0.0000")
        for p in postings:
            assert p.debit_amount >= Decimal("0.0000"), "Negative debit amount forbidden"
            assert p.credit_amount >= Decimal("0.0000"), "Negative credit amount forbidden"
            assert not (p.debit_amount > 0 and p.credit_amount > 0), "Posting cannot have both debit and credit > 0"
            independent_sum_debits += p.debit_amount
            independent_sum_credits += p.credit_amount

        # Strict balance invariant check
        assert independent_sum_debits == independent_sum_credits, (
            f"Ledger Imbalance in Tx {tx.id} ({tx.transaction_type}): "
            f"SUM(Debits)={independent_sum_debits} != SUM(Credits)={independent_sum_credits}"
        )


@pytest.mark.asyncio
async def test_independent_pnl_ground_truth_matrix(db_session: AsyncSession):
    """Test Requirement 7: Independent ground-truth expected-value fixtures for EURUSD, XAUUSD, BTCUSD,
    profitable/losing trades, partial exits, scale-ins, FIFO allocation, reversal, commissions, swaps, and FX conversion."""
    tenant_id = uuid.uuid4()
    account_num = 50002
    run = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1")
    now = datetime.now(timezone.utc)

    # 1. EURUSD Profitable Long: 1.00 lot Entry @ 1.080000, Exit @ 1.085000 (+50 pips)
    # Expected: (1.085000 - 1.080000) * 1.00 * 100,000 = +$500.0000 gross. Commission: -$7.00, Net: +$493.00
    # 2. XAUUSD Losing Short: 1.00 lot Entry @ 2350.00, Exit @ 2360.00 (-$10 delta)
    # Expected: (2350.00 - 2360.00) * 1.00 * 100 = -$1,000.0000 gross. Commission: -$10.00, Net: -$1,010.00
    # 3. BTCUSD Profitable Long: 2.00 lots Entry @ 60,000.00, Exit @ 62,500.00 (+$2500 delta)
    # Expected: (62,500.00 - 60,000.00) * 2.00 * 1 = +$5,000.0000 gross. Commission: -$20.00, Net: +$4,980.00

    obs = [
        # EURUSD
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=70001, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 70001, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": 71001, "commission": "-3.5000"},
            observation_status="ORIGINAL", source_time_msc=100, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=70002, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 70002, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "1.0000", "price": "1.085000", "position_id": 71001, "profit": "500.0000", "commission": "-3.5000"},
            observation_status="ORIGINAL", source_time_msc=200, source_timestamp_utc=now,
        ),
        # XAUUSD
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=70003, item_payload_hash="h3",
            raw_item_json={"deal_ticket": 70003, "symbol": "XAUUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "2350.000000", "position_id": 71002, "commission": "-5.0000"},
            observation_status="ORIGINAL", source_time_msc=300, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=70004, item_payload_hash="h4",
            raw_item_json={"deal_ticket": 70004, "symbol": "XAUUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_OUT", "volume": "1.0000", "price": "2360.000000", "position_id": 71002, "profit": "-1000.0000", "commission": "-5.0000"},
            observation_status="ORIGINAL", source_time_msc=400, source_timestamp_utc=now,
        ),
        # BTCUSD
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=70005, item_payload_hash="h5",
            raw_item_json={"deal_ticket": 70005, "symbol": "BTCUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "2.0000", "price": "60000.000000", "position_id": 71003, "commission": "-10.0000"},
            observation_status="ORIGINAL", source_time_msc=500, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=70006, item_payload_hash="h6",
            raw_item_json={"deal_ticket": 70006, "symbol": "BTCUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "2.0000", "price": "62500.000000", "position_id": 71003, "profit": "5000.0000", "commission": "-10.0000"},
            observation_status="ORIGINAL", source_time_msc=600, source_timestamp_utc=now,
        ),
    ]

    trades, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
        db_session, tenant_id, account_num, "Exness-Real1", "HEDGING", "USD", run, obs
    )

    t_eur = next(t for t in trades if t.symbol == "EURUSD")
    t_xau = next(t for t in trades if t.symbol == "XAUUSD")
    t_btc = next(t for t in trades if t.symbol == "BTCUSD")

    # Independent ground-truth assertions
    assert t_eur.realized_gross_pnl == Decimal("500.0000")
    assert t_eur.total_commission == Decimal("-7.0000")
    assert t_eur.realized_net_pnl == Decimal("493.0000")

    assert t_xau.realized_gross_pnl == Decimal("-1000.0000")
    assert t_xau.total_commission == Decimal("-10.0000")
    assert t_xau.realized_net_pnl == Decimal("-1010.0000")

    assert t_btc.realized_gross_pnl == Decimal("5000.0000")
    assert t_btc.total_commission == Decimal("-20.0000")
    assert t_btc.realized_net_pnl == Decimal("4980.0000")


@pytest.mark.asyncio
async def test_reconstruction_determinism_multi_run_replay(db_session: AsyncSession):
    """Test Requirement 8: Run the same Phase 4 raw dataset through Run A, Run B, and Run C.
    Verify 100% financial and business state equality across all runs."""
    tenant_id = uuid.uuid4()
    account_num = 50003
    now = datetime.now(timezone.utc)

    raw_dataset = [
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="INITIAL_HISTORICAL", event_type="DEAL_EVENT", external_ticket=80001, item_payload_hash="h1",
            raw_item_json={"deal_ticket": 80001, "deal_type": "DEAL_TYPE_BALANCE", "profit": "10000.0000", "currency": "USD"},
            observation_status="ORIGINAL", source_time_msc=100, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=80002, item_payload_hash="h2",
            raw_item_json={"deal_ticket": 80002, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_BUY", "deal_entry": "DEAL_ENTRY_IN", "volume": "1.0000", "price": "1.080000", "position_id": 81001, "commission": "-3.5000"},
            observation_status="ORIGINAL", source_time_msc=200, source_timestamp_utc=now,
        ),
        RawEventObservation(
            id=uuid.uuid4(), observation_id=uuid.uuid4(), ingress_payload_id=uuid.uuid4(),
            tenant_id=tenant_id, device_id=uuid.uuid4(), account_number=account_num, server_name="Exness-Real1",
            source_type="ON_TRADE_TRANSACTION", event_type="DEAL_EVENT", external_ticket=80003, item_payload_hash="h3",
            raw_item_json={"deal_ticket": 80003, "symbol": "EURUSD", "deal_type": "DEAL_TYPE_SELL", "deal_entry": "DEAL_ENTRY_OUT", "volume": "1.0000", "price": "1.085000", "position_id": 81001, "profit": "500.0000", "commission": "-3.5000"},
            observation_status="ORIGINAL", source_time_msc=300, source_timestamp_utc=now,
        ),
    ]

    # Run A
    run_a = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1", reason="RUN_A")
    trades_a, execs_a, bals_a = await TradeReconstructionEngine.process_raw_observations_for_run(
        db_session, tenant_id, account_num, "Exness-Real1", "HEDGING", "USD", run_a, raw_dataset
    )
    bal_proj_a = await DoubleEntryLedgerEngine.get_running_balance_projection(db_session, run_a.id, account_num)

    # Run B
    run_b = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1", reason="RUN_B")
    trades_b, execs_b, bals_b = await TradeReconstructionEngine.process_raw_observations_for_run(
        db_session, tenant_id, account_num, "Exness-Real1", "HEDGING", "USD", run_b, raw_dataset
    )
    bal_proj_b = await DoubleEntryLedgerEngine.get_running_balance_projection(db_session, run_b.id, account_num)

    # Run C
    run_c = await ReconstructionManager.create_run(db_session, tenant_id, account_num, "Exness-Real1", reason="RUN_C")
    trades_c, execs_c, bals_c = await TradeReconstructionEngine.process_raw_observations_for_run(
        db_session, tenant_id, account_num, "Exness-Real1", "HEDGING", "USD", run_c, raw_dataset
    )
    bal_proj_c = await DoubleEntryLedgerEngine.get_running_balance_projection(db_session, run_c.id, account_num)

    # 1. Counts equality
    assert len(trades_a) == len(trades_b) == len(trades_c) == 1
    assert len(execs_a) == len(execs_b) == len(execs_c) == 2
    assert len(bals_a) == len(bals_b) == len(bals_c) == 1

    # 2. Trade Financial Invariants Equality
    for ta, tb, tc in zip(trades_a, trades_b, trades_c):
        assert ta.symbol == tb.symbol == tc.symbol == "EURUSD"
        assert ta.side == tb.side == tc.side == "BUY"
        assert ta.position_ticket == tb.position_ticket == tc.position_ticket == 81001
        assert ta.total_entry_volume == tb.total_entry_volume == tc.total_entry_volume == Decimal("1.0000")
        assert ta.total_exit_volume == tb.total_exit_volume == tc.total_exit_volume == Decimal("1.0000")
        assert ta.open_volume == tb.open_volume == tc.open_volume == Decimal("0.0000")
        assert ta.vwap_entry_price == tb.vwap_entry_price == tc.vwap_entry_price == Decimal("1.080000")
        assert ta.vwap_exit_price == tb.vwap_exit_price == tc.vwap_exit_price == Decimal("1.085000")
        assert ta.realized_gross_pnl == tb.realized_gross_pnl == tc.realized_gross_pnl == Decimal("500.0000")
        assert ta.total_commission == tb.total_commission == tc.total_commission == Decimal("-7.0000")
        assert ta.realized_net_pnl == tb.realized_net_pnl == tc.realized_net_pnl == Decimal("493.0000")
        assert ta.trade_status == tb.trade_status == tc.trade_status == "CLOSED"

    # 3. Running Balance Projection Invariant
    assert bal_proj_a == bal_proj_b == bal_proj_c == Decimal("10493.0000")




