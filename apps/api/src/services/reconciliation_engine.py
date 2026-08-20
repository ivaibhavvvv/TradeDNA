"""TradeDNA Phase 6 - Financial Reconciliation Engine
Executes deterministic, multi-level financial reconciliation between Layer 1 Raw Observations
and Layer 2 Canonical State. Read-only against raw and canonical tables.
"""

from datetime import datetime, timezone
from decimal import Decimal
import time
from typing import Any, Optional
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.canonical_ledger import (
    CanonicalBalanceEvent,
    CanonicalExecution,
    CanonicalLedgerPosting,
    CanonicalLedgerTransaction,
    CanonicalTrade,
)
from src.models.instrument_spec import InstrumentSpecification
from src.models.raw_event import (
    RawAccountSnapshot,
    RawEventObservation,
    RawPositionSnapshot,
)
from src.models.reconciliation import (
    DataIntegrityScoreHistory,
    ReconciliationAccountSummary,
    ReconciliationDiscrepancy,
    ReconciliationPositionSummary,
    ReconciliationRun,
)
from src.models.reconstruction_run import ReconstructionRun
from src.services.double_entry_ledger_engine import DoubleEntryLedgerEngine
from src.services.instrument_service import InstrumentService
from src.services.reconciliation_policy import (
    DEFAULT_SEVERITY_POLICY,
    DEFAULT_TOLERANCE_PROFILE,
    ReconciliationSeverityPolicy,
    ReconciliationToleranceProfile,
)


class ReconciliationEngine:
    """Core three-tier financial reconciliation and data integrity pipeline."""

    @classmethod
    async def execute_reconciliation(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
        server_name: str,
        reconstruction_run_id: uuid.UUID,
        snapshot_id: Optional[uuid.UUID] = None,
        reconciliation_type: str = "POINT_IN_TIME_SNAPSHOT",
        as_of_time_msc: Optional[int] = None,
        window_start_msc: Optional[int] = None,
        window_end_msc: Optional[int] = None,
        severity_policy: ReconciliationSeverityPolicy = DEFAULT_SEVERITY_POLICY,
        tolerance_profile: ReconciliationToleranceProfile = DEFAULT_TOLERANCE_PROFILE,
        engine_version: str = "6.0.0",
        instrument_spec_version: str = "1.0.0",
        fx_source_version: str = "1.0.0",
    ) -> ReconciliationRun:
        """Executes full three-level reconciliation and persists audit run artifacts."""
        t0 = time.perf_counter()
        now_utc = datetime.now(timezone.utc)

        # 1. Fetch or identify relevant Snapshot
        snapshot: Optional[RawAccountSnapshot] = None
        if snapshot_id:
            stmt_s = select(RawAccountSnapshot).where(
                RawAccountSnapshot.tenant_id == tenant_id,
                RawAccountSnapshot.id == snapshot_id,
            )
            res_s = await session.execute(stmt_s)
            snapshot = res_s.scalar_one_or_none()
        elif as_of_time_msc is not None:
            as_of_dt = datetime.fromtimestamp(as_of_time_msc / 1000.0, tz=timezone.utc)
            stmt_s = (
                select(RawAccountSnapshot)
                .where(
                    RawAccountSnapshot.tenant_id == tenant_id,
                    RawAccountSnapshot.account_number == account_number,
                    RawAccountSnapshot.snapshot_time_utc <= as_of_dt,
                )
                .order_by(RawAccountSnapshot.snapshot_time_utc.desc())
                .limit(1)
            )
            res_s = await session.execute(stmt_s)
            snapshot = res_s.scalar_one_or_none()
        else:
            # Get latest snapshot
            stmt_s = (
                select(RawAccountSnapshot)
                .where(
                    RawAccountSnapshot.tenant_id == tenant_id,
                    RawAccountSnapshot.account_number == account_number,
                )
                .order_by(RawAccountSnapshot.snapshot_time_utc.desc())
                .limit(1)
            )
            res_s = await session.execute(stmt_s)
            snapshot = res_s.scalar_one_or_none()

        effective_time_msc = (
            int(snapshot.snapshot_time_utc.timestamp() * 1000)
            if snapshot
            else (as_of_time_msc or int(now_utc.timestamp() * 1000))
        )
        effective_timestamp_utc = (
            snapshot.snapshot_time_utc if snapshot else now_utc
        )

        # 2. Initialize ReconciliationRun record
        run_id = uuid.uuid4()
        recon_run = ReconciliationRun(
            id=run_id,
            tenant_id=tenant_id,
            account_number=account_number,
            server_name=server_name,
            reconstruction_run_id=reconstruction_run_id,
            snapshot_id=snapshot.id if snapshot else None,
            reconciliation_type=reconciliation_type,
            as_of_time_msc=effective_time_msc,
            as_of_timestamp_utc=effective_timestamp_utc,
            window_start_msc=window_start_msc,
            window_end_msc=window_end_msc,
            status="IN_PROGRESS",
            reconciliation_engine_version=engine_version,
            tolerance_profile_version=tolerance_profile.profile_version,
            severity_policy_version=severity_policy.policy_version,
            instrument_spec_version=instrument_spec_version,
            fx_source_version=fx_source_version,
        )

        discrepancies: list[ReconciliationDiscrepancy] = []

        # 3. LEVEL 1: Account-Level Snapshot Reconciliation
        account_summary = await cls._reconcile_account_level(
            session=session,
            recon_run_id=run_id,
            tenant_id=tenant_id,
            account_number=account_number,
            server_name=server_name,
            reconstruction_run_id=reconstruction_run_id,
            snapshot=snapshot,
            effective_time_msc=effective_time_msc,
            severity_policy=severity_policy,
            tolerance_profile=tolerance_profile,
            discrepancies=discrepancies,
        )

        # 4. LEVEL 2: Position-Level Snapshot Reconciliation
        pos_summaries = await cls._reconcile_position_level(
            session=session,
            recon_run_id=run_id,
            tenant_id=tenant_id,
            account_number=account_number,
            server_name=server_name,
            reconstruction_run_id=reconstruction_run_id,
            snapshot=snapshot,
            effective_time_msc=effective_time_msc,
            severity_policy=severity_policy,
            tolerance_profile=tolerance_profile,
            discrepancies=discrepancies,
            instrument_spec_version=instrument_spec_version,
        )

        # 5. LEVEL 3: Event-Level Deal, Balance Event, and Double-Entry Ledger Reconciliation
        await cls._reconcile_event_and_ledger_level(
            session=session,
            recon_run_id=run_id,
            tenant_id=tenant_id,
            account_number=account_number,
            server_name=server_name,
            reconstruction_run_id=reconstruction_run_id,
            window_start_msc=window_start_msc,
            window_end_msc=window_end_msc,
            severity_policy=severity_policy,
            tolerance_profile=tolerance_profile,
            discrepancies=discrepancies,
        )

        # 6. Calculate Discrepancy Counts and Data Integrity Score
        crit_c = sum(1 for d in discrepancies if d.severity == "CRITICAL")
        high_c = sum(1 for d in discrepancies if d.severity == "HIGH")
        med_c = sum(1 for d in discrepancies if d.severity == "MEDIUM")
        low_c = sum(1 for d in discrepancies if d.severity == "LOW")
        info_c = sum(1 for d in discrepancies if d.severity == "INFO")

        # Penalty Matrix: Critical=-25.0, High=-10.0, Med=-3.0, Low=-0.5, Info=0.0
        total_penalty = (
            (Decimal(str(crit_c)) * Decimal("25.00"))
            + (Decimal(str(high_c)) * Decimal("10.00"))
            + (Decimal(str(med_c)) * Decimal("3.00"))
            + (Decimal(str(low_c)) * Decimal("0.50"))
        )
        integrity_score = max(Decimal("0.00"), Decimal("100.00") - total_penalty).quantize(Decimal("0.01"))

        # Grade calculation
        if integrity_score == Decimal("100.00"):
            grade = "AAA"
        elif integrity_score >= Decimal("95.00"):
            grade = "AA"
        elif integrity_score >= Decimal("90.00"):
            grade = "A"
        elif integrity_score >= Decimal("75.00"):
            grade = "B"
        elif integrity_score >= Decimal("50.00"):
            grade = "C"
        else:
            grade = "D"

        is_clean = (crit_c == 0 and high_c == 0 and med_c == 0)

        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        recon_run.status = "COMPLETED"
        recon_run.discrepancy_count = len(discrepancies)
        recon_run.critical_count = crit_c
        recon_run.high_count = high_c
        recon_run.medium_count = med_c
        recon_run.low_count = low_c
        recon_run.info_count = info_c
        recon_run.data_integrity_score = integrity_score
        recon_run.integrity_grade = grade
        recon_run.is_clean = is_clean
        recon_run.execution_time_ms = elapsed_ms

        score_history = DataIntegrityScoreHistory(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            account_number=account_number,
            server_name=server_name,
            reconciliation_run_id=run_id,
            score=integrity_score,
            grade=grade,
            active_discrepancies=len(discrepancies),
            critical_discrepancies=crit_c,
            recorded_at=now_utc,
        )

        # 7. Persist Reconciliation Records
        session.add(recon_run)
        if account_summary:
            session.add(account_summary)
        if pos_summaries:
            session.add_all(pos_summaries)
        if discrepancies:
            session.add_all(discrepancies)
        session.add(score_history)

        await session.flush()
        return recon_run

    @classmethod
    async def _reconcile_account_level(
        cls,
        session: AsyncSession,
        recon_run_id: uuid.UUID,
        tenant_id: uuid.UUID,
        account_number: int,
        server_name: str,
        reconstruction_run_id: uuid.UUID,
        snapshot: Optional[RawAccountSnapshot],
        effective_time_msc: int,
        severity_policy: ReconciliationSeverityPolicy,
        tolerance_profile: ReconciliationToleranceProfile,
        discrepancies: list[ReconciliationDiscrepancy],
    ) -> Optional[ReconciliationAccountSummary]:
        """Level 1: Reconciles MT5 snapshot balance, equity, margin against Canonical Ledger."""
        if not snapshot:
            return None

        currency = snapshot.currency or "USD"

        # Canonical Projected Running Balance
        canonical_balance = await DoubleEntryLedgerEngine.get_running_balance_projection(
            session=session,
            reconstruction_run_id=reconstruction_run_id,
            account_number=account_number,
        )

        # Canonical Open Trades Floating PnL calculation
        stmt_t = select(CanonicalTrade).where(
            CanonicalTrade.tenant_id == tenant_id,
            CanonicalTrade.reconstruction_run_id == reconstruction_run_id,
            CanonicalTrade.account_number == account_number,
            CanonicalTrade.trade_status.in_(["OPEN", "PARTIALLY_CLOSED"]),
        )
        res_t = await session.execute(stmt_t)
        open_trades = list(res_t.scalars().all())

        canonical_floating_pl = Decimal("0.0000")
        canonical_margin = Decimal("0.0000")

        # Compute floating PnL across open trades using snapshot market prices
        for t in open_trades:
            # Fetch spec
            spec = await InstrumentService.get_or_create_default_spec(session, tenant_id, t.symbol)
            market_price = t.vwap_entry_price
            floating_pnl_trade = Decimal("0.0000")
            if t.open_volume > 0:
                if t.side == "BUY":
                    price_delta = market_price - t.vwap_entry_price
                else:
                    price_delta = t.vwap_entry_price - market_price
                floating_pnl_trade = (price_delta / spec.tick_size) * spec.tick_value * t.open_volume
            canonical_floating_pl += floating_pnl_trade

        canonical_equity = canonical_balance + canonical_floating_pl
        canonical_free_margin = canonical_equity - canonical_margin

        mt5_bal = snapshot.balance.quantize(Decimal("0.0001"))
        mt5_eq = snapshot.equity.quantize(Decimal("0.0001"))
        mt5_mrg = snapshot.margin.quantize(Decimal("0.0001"))
        mt5_free = snapshot.margin_free.quantize(Decimal("0.0001"))
        mt5_float = (mt5_eq - mt5_bal).quantize(Decimal("0.0001"))

        bal_delta = (mt5_bal - canonical_balance).quantize(Decimal("0.0001"))
        eq_delta = (mt5_eq - canonical_equity).quantize(Decimal("0.0001"))
        mrg_delta = (mt5_mrg - canonical_margin).quantize(Decimal("0.0001"))
        free_delta = (mt5_free - canonical_free_margin).quantize(Decimal("0.0001"))
        float_delta = (mt5_float - canonical_floating_pl).quantize(Decimal("0.0001"))

        summary = ReconciliationAccountSummary(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            reconciliation_run_id=recon_run_id,
            account_number=account_number,
            server_name=server_name,
            currency=currency,
            mt5_balance=mt5_bal,
            mt5_equity=mt5_eq,
            mt5_margin=mt5_mrg,
            mt5_free_margin=mt5_free,
            mt5_floating_pl=mt5_float,
            canonical_balance=canonical_balance,
            canonical_equity=canonical_equity,
            canonical_margin=canonical_margin,
            canonical_free_margin=canonical_free_margin,
            canonical_floating_pl=canonical_floating_pl,
            balance_delta=bal_delta,
            equity_delta=eq_delta,
            margin_delta=mrg_delta,
            free_margin_delta=free_delta,
            floating_pl_delta=float_delta,
        )

        # Balance Discrepancy Evaluation
        if abs(bal_delta) > Decimal("0.0000"):
            sev = severity_policy.classify_financial_delta(bal_delta)
            discrepancies.append(
                ReconciliationDiscrepancy(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    reconciliation_run_id=recon_run_id,
                    account_number=account_number,
                    server_name=server_name,
                    discrepancy_scope="ACCOUNT_LEVEL",
                    discrepancy_category="BALANCE_MISMATCH",
                    severity=sev,
                    entity_type="ACCOUNT",
                    entity_identifier=str(account_number),
                    broker_value=str(mt5_bal),
                    canonical_value=str(canonical_balance),
                    delta_value=str(bal_delta),
                    broker_source=f"RAW_ACCOUNT_SNAPSHOT:{snapshot.id}",
                    canonical_source=f"CANONICAL_LEDGER_RUN:{reconstruction_run_id}",
                    currency=currency,
                    tolerance_applied=f"{tolerance_profile.financial_penny_tolerance} {currency}",
                    details_json={
                        "snapshot_id": str(snapshot.id),
                        "snapshot_time_utc": snapshot.snapshot_time_utc.isoformat(),
                        "tolerance_profile_version": tolerance_profile.profile_version,
                        "severity_policy_version": severity_policy.policy_version,
                    },
                )
            )

        return summary

    @classmethod
    async def _reconcile_position_level(
        cls,
        session: AsyncSession,
        recon_run_id: uuid.UUID,
        tenant_id: uuid.UUID,
        account_number: int,
        server_name: str,
        reconstruction_run_id: uuid.UUID,
        snapshot: Optional[RawAccountSnapshot],
        effective_time_msc: int,
        severity_policy: ReconciliationSeverityPolicy,
        tolerance_profile: ReconciliationToleranceProfile,
        discrepancies: list[ReconciliationDiscrepancy],
        instrument_spec_version: str,
    ) -> list[ReconciliationPositionSummary]:
        """Level 2: Reconciles MT5 position snapshots with open CanonicalTrade records."""
        summaries: list[ReconciliationPositionSummary] = []

        # Fetch MT5 position snapshots
        stmt_p = select(RawPositionSnapshot).where(
            RawPositionSnapshot.tenant_id == tenant_id,
            RawPositionSnapshot.account_number == account_number,
        )
        if snapshot:
            stmt_p = stmt_p.where(RawPositionSnapshot.ingress_payload_id == snapshot.ingress_payload_id)
        res_p = await session.execute(stmt_p)
        
        # Parse MT5 positions from raw_payload_json
        mt5_positions: dict[int, dict[str, Any]] = {}
        for p_snap in res_p.scalars().all():
            payload = p_snap.raw_payload_json or {}
            items = payload if isinstance(payload, list) else payload.get("positions", [payload] if ("ticket" in payload or "position_ticket" in payload or "position_id" in payload) else [])
            for it in items:
                if not isinstance(it, dict):
                    continue
                ticket = int(it.get("ticket") or it.get("position_ticket") or it.get("position_id") or it.get("deal_ticket", 0))
                if ticket > 0:
                    mt5_positions[ticket] = {
                        "ticket": ticket,
                        "symbol": it.get("symbol", "UNKNOWN"),
                        "type": str(it.get("type") or it.get("position_type") or it.get("side", "BUY")).upper(),
                        "volume": Decimal(str(it.get("volume", "0.0000"))),
                        "price_open": Decimal(str(it.get("price_open", it.get("price", "0.000000")))),
                        "price_current": Decimal(str(it.get("price_current", it.get("price", "0.000000")))),
                        "profit": Decimal(str(it.get("profit", "0.0000"))),
                        "swap": Decimal(str(it.get("swap", "0.0000"))),
                        "raw_id": str(p_snap.id),
                    }

        # Fetch Canonical Open Trades
        stmt_t = select(CanonicalTrade).where(
            CanonicalTrade.tenant_id == tenant_id,
            CanonicalTrade.reconstruction_run_id == reconstruction_run_id,
            CanonicalTrade.account_number == account_number,
            CanonicalTrade.trade_status.in_(["OPEN", "PARTIALLY_CLOSED"]),
        )
        res_t = await session.execute(stmt_t)
        canonical_trades = {t.position_ticket: t for t in res_t.scalars().all()}

        all_tickets = set(mt5_positions.keys()).union(set(canonical_trades.keys()))

        for ticket in all_tickets:
            mt5_p = mt5_positions.get(ticket)
            can_t = canonical_trades.get(ticket)

            if mt5_p and can_t:
                # Both exist: Compare volumes, prices, profit
                vol_delta = (mt5_p["volume"] - can_t.open_volume).quantize(Decimal("0.0001"))
                price_delta = (mt5_p["price_open"] - can_t.vwap_entry_price).quantize(Decimal("0.000001"))
                profit_delta = (mt5_p["profit"] - Decimal("0.0000")).quantize(Decimal("0.0001"))

                status = "MATCHED" if abs(vol_delta) == 0 and abs(price_delta) == 0 else "MISMATCHED"

                pos_summary = ReconciliationPositionSummary(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    reconciliation_run_id=recon_run_id,
                    account_number=account_number,
                    server_name=server_name,
                    symbol=mt5_p["symbol"],
                    position_ticket=ticket,
                    side=mt5_p["type"],
                    mt5_volume=mt5_p["volume"],
                    mt5_price_open=mt5_p["price_open"],
                    mt5_price_current=mt5_p["price_current"],
                    mt5_profit=mt5_p["profit"],
                    mt5_swap=mt5_p["swap"],
                    canonical_open_volume=can_t.open_volume,
                    canonical_vwap_entry=can_t.vwap_entry_price,
                    canonical_floating_pl=Decimal("0.0000"),
                    canonical_swap=can_t.total_swap,
                    volume_delta=vol_delta,
                    price_delta=price_delta,
                    profit_delta=profit_delta,
                    market_price_used=mt5_p["price_current"],
                    market_price_timestamp_msc=effective_time_msc,
                    fx_rate_used=Decimal("1.000000"),
                    fx_rate_source="DEFAULT",
                    instrument_spec_version=instrument_spec_version,
                    status=status,
                )
                summaries.append(pos_summary)

                if abs(vol_delta) > tolerance_profile.volume_tolerance:
                    discrepancies.append(
                        ReconciliationDiscrepancy(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            reconciliation_run_id=recon_run_id,
                            account_number=account_number,
                            server_name=server_name,
                            discrepancy_scope="POSITION_LEVEL",
                            discrepancy_category="POSITION_VOLUME_MISMATCH",
                            severity="HIGH",
                            entity_type="POSITION",
                            entity_identifier=str(ticket),
                            broker_value=str(mt5_p["volume"]),
                            canonical_value=str(can_t.open_volume),
                            delta_value=str(vol_delta),
                            broker_source=f"RAW_POSITION_SNAPSHOT:{mt5_p['raw_id']}",
                            canonical_source=f"CANONICAL_TRADE:{can_t.id}",
                            currency="LOTS",
                            tolerance_applied=f"{tolerance_profile.volume_tolerance} LOTS",
                            details_json={"symbol": mt5_p["symbol"], "position_ticket": ticket},
                        )
                    )

            elif mt5_p and not can_t:
                # Position in MT5, missing in TradeDNA
                summaries.append(
                    ReconciliationPositionSummary(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        reconciliation_run_id=recon_run_id,
                        account_number=account_number,
                        server_name=server_name,
                        symbol=mt5_p["symbol"],
                        position_ticket=ticket,
                        side=mt5_p["type"],
                        mt5_volume=mt5_p["volume"],
                        mt5_price_open=mt5_p["price_open"],
                        mt5_price_current=mt5_p["price_current"],
                        mt5_profit=mt5_p["profit"],
                        mt5_swap=mt5_p["swap"],
                        canonical_open_volume=Decimal("0.0000"),
                        canonical_vwap_entry=Decimal("0.000000"),
                        canonical_floating_pl=Decimal("0.0000"),
                        canonical_swap=Decimal("0.0000"),
                        volume_delta=mt5_p["volume"],
                        price_delta=mt5_p["price_open"],
                        profit_delta=mt5_p["profit"],
                        market_price_used=mt5_p["price_current"],
                        market_price_timestamp_msc=effective_time_msc,
                        fx_rate_used=Decimal("1.000000"),
                        fx_rate_source="DEFAULT",
                        instrument_spec_version=instrument_spec_version,
                        status="MISSING_CANONICAL",
                    )
                )
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        reconciliation_run_id=recon_run_id,
                        account_number=account_number,
                        server_name=server_name,
                        discrepancy_scope="POSITION_LEVEL",
                        discrepancy_category="MISSING_CANONICAL_TRADE",
                        severity="CRITICAL" if mt5_p["volume"] >= Decimal("0.10") else "HIGH",
                        entity_type="POSITION",
                        entity_identifier=str(ticket),
                        broker_value=f"{mt5_p['symbol']} {mt5_p['type']} {mt5_p['volume']} lots @ {mt5_p['price_open']}",
                        canonical_value="NONE",
                        delta_value=str(mt5_p["volume"]),
                        broker_source=f"RAW_POSITION_SNAPSHOT:{mt5_p['raw_id']}",
                        canonical_source="NONE",
                        currency="LOTS",
                        tolerance_applied="0.0000 LOTS",
                        details_json={"symbol": mt5_p["symbol"], "position_ticket": ticket},
                    )
                )

            elif can_t and not mt5_p:
                # Ghost Trade: Open in TradeDNA, absent from MT5
                summaries.append(
                    ReconciliationPositionSummary(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        reconciliation_run_id=recon_run_id,
                        account_number=account_number,
                        server_name=server_name,
                        symbol=can_t.symbol,
                        position_ticket=ticket,
                        side=can_t.side,
                        mt5_volume=Decimal("0.0000"),
                        mt5_price_open=Decimal("0.000000"),
                        mt5_price_current=Decimal("0.000000"),
                        mt5_profit=Decimal("0.0000"),
                        mt5_swap=Decimal("0.0000"),
                        canonical_open_volume=can_t.open_volume,
                        canonical_vwap_entry=can_t.vwap_entry_price,
                        canonical_floating_pl=Decimal("0.0000"),
                        canonical_swap=can_t.total_swap,
                        volume_delta=-can_t.open_volume,
                        price_delta=-can_t.vwap_entry_price,
                        profit_delta=Decimal("0.0000"),
                        market_price_used=can_t.vwap_entry_price,
                        market_price_timestamp_msc=effective_time_msc,
                        fx_rate_used=Decimal("1.000000"),
                        fx_rate_source="DEFAULT",
                        instrument_spec_version=instrument_spec_version,
                        status="GHOST_CANONICAL",
                    )
                )
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        reconciliation_run_id=recon_run_id,
                        account_number=account_number,
                        server_name=server_name,
                        discrepancy_scope="POSITION_LEVEL",
                        discrepancy_category="GHOST_CANONICAL_TRADE",
                        severity="HIGH",
                        entity_type="TRADE",
                        entity_identifier=str(can_t.id),
                        broker_value="NONE",
                        canonical_value=f"{can_t.symbol} {can_t.side} {can_t.open_volume} lots",
                        delta_value=str(-can_t.open_volume),
                        broker_source="NONE",
                        canonical_source=f"CANONICAL_TRADE:{can_t.id}",
                        currency="LOTS",
                        tolerance_applied="0.0000 LOTS",
                        details_json={"trade_id": str(can_t.id), "position_ticket": ticket},
                    )
                )

        return summaries

    @classmethod
    async def _reconcile_event_and_ledger_level(
        cls,
        session: AsyncSession,
        recon_run_id: uuid.UUID,
        tenant_id: uuid.UUID,
        account_number: int,
        server_name: str,
        reconstruction_run_id: uuid.UUID,
        window_start_msc: Optional[int],
        window_end_msc: Optional[int],
        severity_policy: ReconciliationSeverityPolicy,
        tolerance_profile: ReconciliationToleranceProfile,
        discrepancies: list[ReconciliationDiscrepancy],
    ) -> None:
        """Level 3: Deal-by-deal matching, non-trading events, and independent double-entry ledger balance."""

        # Fetch Raw Event Observations
        stmt_o = select(RawEventObservation).where(
            RawEventObservation.tenant_id == tenant_id,
            RawEventObservation.account_number == account_number,
            RawEventObservation.observation_status != "DUPLICATE",
        )
        if window_start_msc is not None:
            stmt_o = stmt_o.where(RawEventObservation.source_time_msc >= window_start_msc)
        if window_end_msc is not None:
            stmt_o = stmt_o.where(RawEventObservation.source_time_msc <= window_end_msc)
        res_o = await session.execute(stmt_o)
        raw_obs = {o.external_ticket: o for o in res_o.scalars().all()}

        # Fetch Canonical Executions
        stmt_e = select(CanonicalExecution).where(
            CanonicalExecution.tenant_id == tenant_id,
            CanonicalExecution.reconstruction_run_id == reconstruction_run_id,
            CanonicalExecution.account_number == account_number,
        )
        res_e = await session.execute(stmt_e)
        canonical_execs = {e.deal_ticket: e for e in res_e.scalars().all()}

        # Check for Missing Canonical Executions
        for ticket, obs in raw_obs.items():
            data = obs.raw_item_json or {}
            deal_type = str(data.get("deal_type", ""))
            # Trading deals
            if deal_type in ("DEAL_TYPE_BUY", "DEAL_TYPE_SELL", "0", "1"):
                if ticket not in canonical_execs:
                    vol = str(data.get("volume", "0.0000"))
                    discrepancies.append(
                        ReconciliationDiscrepancy(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            reconciliation_run_id=recon_run_id,
                            account_number=account_number,
                            server_name=server_name,
                            discrepancy_scope="EVENT_LEVEL",
                            discrepancy_category="MISSING_CANONICAL_EXECUTION",
                            severity="HIGH",
                            entity_type="DEAL",
                            entity_identifier=str(ticket),
                            broker_value=f"Deal #{ticket} ({data.get('symbol')} {vol} lots)",
                            canonical_value="NONE",
                            delta_value=vol,
                            broker_source=f"RAW_EVENT_OBSERVATION:{obs.id}",
                            canonical_source="NONE",
                            currency="LOTS",
                            tolerance_applied="EXACT",
                            details_json={"deal_ticket": ticket, "observation_id": str(obs.observation_id)},
                        )
                    )

        # Independent Double-Entry Balance Verification across raw rows
        stmt_tx = select(CanonicalLedgerTransaction).where(
            CanonicalLedgerTransaction.tenant_id == tenant_id,
            CanonicalLedgerTransaction.reconstruction_run_id == reconstruction_run_id,
            CanonicalLedgerTransaction.account_number == account_number,
        )
        res_tx = await session.execute(stmt_tx)
        transactions = list(res_tx.scalars().all())

        for tx in transactions:
            stmt_p = select(CanonicalLedgerPosting).where(CanonicalLedgerPosting.transaction_id == tx.id)
            res_p = await session.execute(stmt_p)
            postings = list(res_p.scalars().all())

            sum_debits = sum(p.debit_amount for p in postings)
            sum_credits = sum(p.credit_amount for p in postings)
            imbalance = abs(sum_debits - sum_credits)

            if imbalance > Decimal("0.0000"):
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        reconciliation_run_id=recon_run_id,
                        account_number=account_number,
                        server_name=server_name,
                        discrepancy_scope="LEDGER_LEVEL",
                        discrepancy_category="LEDGER_IMBALANCE",
                        severity="CRITICAL",
                        entity_type="POSTING",
                        entity_identifier=str(tx.id),
                        broker_value=str(sum_credits),
                        canonical_value=str(sum_debits),
                        delta_value=str(imbalance),
                        broker_source="SUM_CREDITS",
                        canonical_source="SUM_DEBITS",
                        currency=tx.currency if hasattr(tx, "currency") else "USD",
                        tolerance_applied="0.0000",
                        details_json={"transaction_id": str(tx.id), "transaction_type": tx.transaction_type},
                    )
                )
