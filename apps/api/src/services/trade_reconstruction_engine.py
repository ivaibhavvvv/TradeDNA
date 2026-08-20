"""TradeDNA Phase 5 - Trade Reconstruction Engine
Reconstructs canonical trading executions, Hedging and Netting trade lifecycles,
and balanced double-entry financial ledger records from Layer 1 raw observations.
Optimized for high-volume throughput and deterministic replay.
"""

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.canonical_ledger import (
    CanonicalBalanceEvent,
    CanonicalExecution,
    CanonicalLedgerPosting,
    CanonicalLedgerTransaction,
    CanonicalTrade,
    CanonicalTradeExecutionMap,
)
from src.models.instrument_spec import InstrumentSpecification
from src.models.raw_event import RawEventObservation
from src.models.reconstruction_run import ReconstructionRun
from src.services.double_entry_ledger_engine import DoubleEntryLedgerEngine
from src.services.instrument_service import InstrumentService
from src.services.lot_allocation_engine import EntryLot, LotAllocationEngine


class TradeReconstructionEngine:
    """Core deterministic trade reconstruction and canonical ledger pipeline."""

    @classmethod
    async def process_raw_observations_for_run(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
        server_name: str,
        account_mode: str,  # HEDGING, NETTING
        account_currency: str,
        reconstruction_run: ReconstructionRun,
        raw_observations: list[RawEventObservation],
    ) -> tuple[list[CanonicalTrade], list[CanonicalExecution], list[CanonicalBalanceEvent]]:
        """Processes an ordered list of Layer 1 raw observations and reconstructs
        canonical executions, trades, and double-entry ledger transactions."""

        # 1. Filter duplicate observations and sort chronologically with deterministic tie-breakers
        valid_obs = [o for o in raw_observations if o.observation_status != "DUPLICATE"]
        valid_obs.sort(key=lambda x: (x.source_time_msc, x.external_ticket, str(x.id)))

        executions: list[CanonicalExecution] = []
        balance_events: list[CanonicalBalanceEvent] = []
        balance_txs: list[CanonicalLedgerTransaction] = []
        balance_postings: list[CanonicalLedgerPosting] = []

        conflicted_tickets: set[int] = {
            o.external_ticket for o in raw_observations if o.observation_status == "CONFLICTING"
        }

        # 2. Translate raw observations into Layer 2 canonical executions and balance events
        for obs in valid_obs:
            data = obs.raw_item_json or {}
            deal_type = str(data.get("deal_type", ""))
            deal_ticket = obs.external_ticket

            # Check if this is a non-trading balance event
            if deal_type in ("DEAL_TYPE_BALANCE", "DEAL_TYPE_CREDIT", "DEAL_TYPE_CHARGE",
                             "DEAL_TYPE_CORRECTION", "DEAL_TYPE_BONUS", "DEAL_DIVIDEND",
                             "DEAL_DIVIDEND_FRANKED", "DEAL_TAX", "2", "3", "4", "5", "6", "15", "16", "17"):
                b_type = cls._classify_balance_event_type(deal_type, data.get("profit", "0"))
                amt = Decimal(str(data.get("profit", data.get("amount", "0.0000")))).quantize(Decimal("0.0001"))
                currency = str(data.get("currency", account_currency))
                dt_msc = obs.source_time_msc
                dt_utc = obs.source_timestamp_utc

                bal_event = CanonicalBalanceEvent(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    reconstruction_run_id=reconstruction_run.id,
                    observation_id=obs.observation_id,
                    ingress_payload_id=obs.ingress_payload_id,
                    account_number=account_number,
                    server_name=server_name,
                    event_type=b_type,
                    amount=amt,
                    currency=currency,
                    deal_ticket=deal_ticket,
                    comment=data.get("comment"),
                    event_time_msc=dt_msc,
                    event_timestamp_utc=dt_utc,
                )
                balance_events.append(bal_event)

                # Generate double-entry ledger postings for balance event
                postings = DoubleEntryLedgerEngine.build_balance_event_postings(b_type, amt, currency)
                tx, db_postings = DoubleEntryLedgerEngine.validate_and_create_transaction(
                    tenant_id=tenant_id,
                    reconstruction_run_id=reconstruction_run.id,
                    account_number=account_number,
                    transaction_type=f"CASH_{b_type}",
                    transaction_time_msc=dt_msc,
                    transaction_timestamp_utc=dt_utc,
                    description=f"{b_type} #{deal_ticket}: {amt} {currency}",
                    source_observation_id=obs.observation_id,
                    postings=postings,
                    balance_event_id=bal_event.id,
                )
                balance_txs.append(tx)
                balance_postings.extend(db_postings)

            elif deal_type in ("DEAL_TYPE_BUY", "DEAL_TYPE_SELL", "0", "1"):
                # Trading deal
                side = "BUY" if deal_type in ("DEAL_TYPE_BUY", "0") else "SELL"
                raw_entry = str(data.get("deal_entry", "DEAL_ENTRY_IN"))
                entry_type = cls._normalize_entry_type(raw_entry)
                vol = Decimal(str(data.get("volume", "0.0000"))).quantize(Decimal("0.0001"))
                price = Decimal(str(data.get("price", "0.000000"))).quantize(Decimal("0.000001"))
                sym = str(data.get("symbol", "")).upper().strip()
                pos_ticket = int(data.get("position_id", data.get("position_ticket", 0)))
                order_ticket = int(data.get("order_ticket", data.get("order", 0)))
                counter_pos = int(data["counter_position_ticket"]) if data.get("counter_position_ticket") else None
                counter_deal = int(data["counter_deal_ticket"]) if data.get("counter_deal_ticket") else None

                gross_profit = Decimal(str(data.get("profit", "0.0000"))).quantize(Decimal("0.0001"))
                comm = Decimal(str(data.get("commission", "0.0000"))).quantize(Decimal("0.0001"))
                swap = Decimal(str(data.get("swap", "0.0000"))).quantize(Decimal("0.0001"))
                fee = Decimal(str(data.get("fee", "0.0000"))).quantize(Decimal("0.0001"))

                exec_item = CanonicalExecution(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    reconstruction_run_id=reconstruction_run.id,
                    observation_id=obs.observation_id,
                    ingress_payload_id=obs.ingress_payload_id,
                    account_number=account_number,
                    server_name=server_name,
                    symbol=sym,
                    side=side,
                    entry_type=entry_type,
                    volume=vol,
                    matched_volume=Decimal("0.0000"),
                    price=price,
                    deal_ticket=deal_ticket,
                    order_ticket=order_ticket,
                    position_ticket=pos_ticket,
                    counter_position_ticket=counter_pos,
                    counter_deal_ticket=counter_deal,
                    gross_profit=gross_profit,
                    commission=comm,
                    swap=swap,
                    fee=fee,
                    execution_time_msc=obs.source_time_msc,
                    execution_timestamp_utc=obs.source_timestamp_utc,
                )
                executions.append(exec_item)

        # 3. Execute Trade Reconstruction (Hedging vs Netting)
        reconstructed_trades, all_maps, all_txs, all_postings = await cls._reconstruct_trades(
            session=session,
            tenant_id=tenant_id,
            account_number=account_number,
            server_name=server_name,
            account_mode=account_mode,
            account_currency=account_currency,
            reconstruction_run=reconstruction_run,
            executions=executions,
            conflicted_tickets=conflicted_tickets,
        )

        # 4. Bulk Persist all created entities
        if executions:
            session.add_all(executions)
        if balance_events:
            session.add_all(balance_events)
        if balance_txs:
            session.add_all(balance_txs)
        if balance_postings:
            session.add_all(balance_postings)
        if reconstructed_trades:
            session.add_all(reconstructed_trades)
        if all_maps:
            session.add_all(all_maps)
        if all_txs:
            session.add_all(all_txs)
        if all_postings:
            session.add_all(all_postings)

        await session.flush()
        return reconstructed_trades, executions, balance_events

    @classmethod
    async def _reconstruct_trades(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
        server_name: str,
        account_mode: str,
        account_currency: str,
        reconstruction_run: ReconstructionRun,
        executions: list[CanonicalExecution],
        conflicted_tickets: set[int],
    ) -> tuple[list[CanonicalTrade], list[CanonicalTradeExecutionMap], list[CanonicalLedgerTransaction], list[CanonicalLedgerPosting]]:
        """Dispatches trade reconstruction to Hedging or Netting algorithms."""
        trades: list[CanonicalTrade] = []
        maps: list[CanonicalTradeExecutionMap] = []
        txs: list[CanonicalLedgerTransaction] = []
        postings: list[CanonicalLedgerPosting] = []

        specs_cache: dict[str, InstrumentSpecification] = {}

        if account_mode == "HEDGING":
            # Group by (symbol, position_ticket)
            groups: dict[tuple[str, int], list[CanonicalExecution]] = defaultdict(list)
            for e in executions:
                groups[(e.symbol, e.position_ticket)].append(e)

            for (sym, pos_ticket), exec_list in groups.items():
                exec_list.sort(key=lambda x: (x.execution_time_msc, x.deal_ticket))
                if sym not in specs_cache:
                    specs_cache[sym] = await InstrumentService.get_or_create_default_spec(session, tenant_id, sym, exec_list[0].execution_timestamp_utc)
                spec = specs_cache[sym]

                trade, t_maps, t_tx, t_postings = await cls._reconstruct_single_hedging_position(
                    session=session,
                    tenant_id=tenant_id,
                    reconstruction_run_id=reconstruction_run.id,
                    account_number=account_number,
                    server_name=server_name,
                    symbol=sym,
                    position_ticket=pos_ticket,
                    exec_list=exec_list,
                    spec=spec,
                    account_currency=account_currency,
                    conflicted_tickets=conflicted_tickets,
                )
                trades.append(trade)
                maps.extend(t_maps)
                if t_tx:
                    txs.append(t_tx)
                    postings.extend(t_postings)

        else:  # NETTING
            # Group by symbol
            groups_net: dict[str, list[CanonicalExecution]] = defaultdict(list)
            for e in executions:
                groups_net[e.symbol].append(e)

            for sym, exec_list in groups_net.items():
                exec_list.sort(key=lambda x: (x.execution_time_msc, x.deal_ticket))
                if sym not in specs_cache:
                    specs_cache[sym] = await InstrumentService.get_or_create_default_spec(session, tenant_id, sym, exec_list[0].execution_timestamp_utc)
                spec = specs_cache[sym]

                net_trades, n_maps, n_txs, n_postings = await cls._reconstruct_netting_symbol_stream(
                    session=session,
                    tenant_id=tenant_id,
                    reconstruction_run_id=reconstruction_run.id,
                    account_number=account_number,
                    server_name=server_name,
                    symbol=sym,
                    exec_list=exec_list,
                    spec=spec,
                    account_currency=account_currency,
                    conflicted_tickets=conflicted_tickets,
                )
                trades.extend(net_trades)
                maps.extend(n_maps)
                txs.extend(n_txs)
                postings.extend(n_postings)

        return trades, maps, txs, postings

    @classmethod
    async def _reconstruct_single_hedging_position(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        reconstruction_run_id: uuid.UUID,
        account_number: int,
        server_name: str,
        symbol: str,
        position_ticket: int,
        exec_list: list[CanonicalExecution],
        spec: InstrumentSpecification,
        account_currency: str,
        conflicted_tickets: set[int],
    ) -> tuple[CanonicalTrade, list[CanonicalTradeExecutionMap], Optional[CanonicalLedgerTransaction], list[CanonicalLedgerPosting]]:
        """Reconstructs a single position in Hedging mode based on MT5 position_ticket."""
        first_entry = next((e for e in exec_list if e.entry_type == "ENTRY_IN"), exec_list[0])
        trade_id = uuid.uuid4()
        side = first_entry.side
        is_conflicted = any(e.deal_ticket in conflicted_tickets for e in exec_list)

        trade = CanonicalTrade(
            id=trade_id,
            tenant_id=tenant_id,
            reconstruction_run_id=reconstruction_run_id,
            account_number=account_number,
            server_name=server_name,
            symbol=symbol,
            side=side,
            account_mode="HEDGING",
            position_ticket=position_ticket,
            total_entry_volume=Decimal("0.0000"),
            total_exit_volume=Decimal("0.0000"),
            open_volume=Decimal("0.0000"),
            vwap_entry_price=first_entry.price,
            vwap_exit_price=None,
            realized_gross_pnl=Decimal("0.0000"),
            total_commission=Decimal("0.0000"),
            total_swap=Decimal("0.0000"),
            total_fees=Decimal("0.0000"),
            realized_net_pnl=Decimal("0.0000"),
            trade_status="OPEN",
            opened_at_msc=exec_list[0].execution_time_msc,
            opened_at_utc=exec_list[0].execution_timestamp_utc,
        )

        open_lots: list[EntryLot] = []
        out_maps: list[CanonicalTradeExecutionMap] = []
        entry_dollar_vol = Decimal("0.0")
        exit_dollar_vol = Decimal("0.0")
        has_unmatched_exit = False

        for e in exec_list:
            trade.total_commission += e.commission
            trade.total_swap += e.swap
            trade.total_fees += e.fee

            if e.entry_type == "ENTRY_IN":
                trade.total_entry_volume += e.volume
                trade.open_volume += e.volume
                entry_dollar_vol += (e.volume * e.price)
                open_lots.append(
                    EntryLot(
                        execution_id=e.id,
                        initial_volume=e.volume,
                        remaining_volume=e.volume,
                        price=e.price,
                        side=e.side,
                        commission=e.commission,
                        fee=e.fee,
                        timestamp_msc=e.execution_time_msc,
                    )
                )

            elif e.entry_type in ("ENTRY_OUT", "ENTRY_OUT_BY"):
                trade.total_exit_volume += e.volume
                trade.open_volume = max(Decimal("0.0000"), trade.open_volume - e.volume)
                exit_dollar_vol += (e.volume * e.price)

                if not open_lots:
                    has_unmatched_exit = True
                else:
                    fx_rate = await InstrumentService.resolve_fx_rate(
                        session=session,
                        tenant_id=tenant_id,
                        from_currency=spec.profit_currency,
                        to_currency=account_currency,
                        timestamp_msc=e.execution_time_msc,
                    )
                    chunk_maps, chunk_pnl = LotAllocationEngine.match_exit_against_lots(
                        trade_id=trade_id,
                        open_lots=open_lots,
                        exit_exec=e,
                        spec=spec,
                        fx_rate=fx_rate,
                    )
                    trade.realized_gross_pnl += chunk_pnl
                    out_maps.extend(chunk_maps)

        # Calculate derived analytical VWAPs
        if trade.total_entry_volume > Decimal("0.0000"):
            trade.vwap_entry_price = (entry_dollar_vol / trade.total_entry_volume).quantize(Decimal("0.000001"))
        if trade.total_exit_volume > Decimal("0.0000"):
            trade.vwap_exit_price = (exit_dollar_vol / trade.total_exit_volume).quantize(Decimal("0.000001"))

        trade.realized_net_pnl = (trade.realized_gross_pnl + trade.total_commission + trade.total_swap + trade.total_fees).quantize(Decimal("0.0001"))

        # Determine status
        if is_conflicted:
            trade.trade_status = "CONFLICTED"
        elif has_unmatched_exit:
            trade.trade_status = "UNMATCHED"
        elif trade.open_volume == Decimal("0.0000"):
            trade.trade_status = "CLOSED"
            trade.closed_at_msc = exec_list[-1].execution_time_msc
            trade.closed_at_utc = exec_list[-1].execution_timestamp_utc
            trade.duration_seconds = max(0, int((exec_list[-1].execution_time_msc - trade.opened_at_msc) / 1000))
        elif trade.total_exit_volume > Decimal("0.0000"):
            trade.trade_status = "PARTIALLY_CLOSED"

        # Record double-entry ledger transaction if trade settled
        tx = None
        db_postings = []
        if trade.trade_status in ("CLOSED", "PARTIALLY_CLOSED") and not is_conflicted:
            postings = DoubleEntryLedgerEngine.build_trade_settlement_postings(trade, account_currency)
            tx, db_postings = DoubleEntryLedgerEngine.validate_and_create_transaction(
                tenant_id=tenant_id,
                reconstruction_run_id=reconstruction_run_id,
                account_number=account_number,
                transaction_type="TRADE_SETTLEMENT",
                transaction_time_msc=exec_list[-1].execution_time_msc,
                transaction_timestamp_utc=exec_list[-1].execution_timestamp_utc,
                description=f"Trade #{trade.position_ticket} ({trade.symbol} {trade.side}): PnL={trade.realized_gross_pnl}",
                source_observation_id=exec_list[-1].observation_id,
                postings=postings,
                trade_id=trade.id,
            )

        return trade, out_maps, tx, db_postings

    @classmethod
    async def _reconstruct_netting_symbol_stream(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        reconstruction_run_id: uuid.UUID,
        account_number: int,
        server_name: str,
        symbol: str,
        exec_list: list[CanonicalExecution],
        spec: InstrumentSpecification,
        account_currency: str,
        conflicted_tickets: set[int],
    ) -> tuple[list[CanonicalTrade], list[CanonicalTradeExecutionMap], list[CanonicalLedgerTransaction], list[CanonicalLedgerPosting]]:
        """Reconstructs positions and trades in Netting mode with FIFO matching and INOUT reversals."""
        net_trades: list[CanonicalTrade] = []
        net_maps: list[CanonicalTradeExecutionMap] = []
        net_txs: list[CanonicalLedgerTransaction] = []
        net_postings: list[CanonicalLedgerPosting] = []

        open_lots: list[EntryLot] = []
        current_trade: Optional[CanonicalTrade] = None
        entry_dollar_vol = Decimal("0.0")
        exit_dollar_vol = Decimal("0.0")

        for e in exec_list:
            is_conflicted = e.deal_ticket in conflicted_tickets

            # Check if this execution opens or increases current position
            if current_trade is None:
                # Open new netting trade
                t_id = uuid.uuid4()
                current_trade = CanonicalTrade(
                    id=t_id,
                    tenant_id=tenant_id,
                    reconstruction_run_id=reconstruction_run_id,
                    account_number=account_number,
                    server_name=server_name,
                    symbol=symbol,
                    side=e.side,
                    account_mode="NETTING",
                    position_ticket=e.position_ticket or e.deal_ticket,
                    total_entry_volume=e.volume,
                    total_exit_volume=Decimal("0.0000"),
                    open_volume=e.volume,
                    vwap_entry_price=e.price,
                    vwap_exit_price=None,
                    realized_gross_pnl=Decimal("0.0000"),
                    total_commission=e.commission,
                    total_swap=e.swap,
                    total_fees=e.fee,
                    realized_net_pnl=Decimal("0.0000"),
                    trade_status="OPEN" if not is_conflicted else "CONFLICTED",
                    opened_at_msc=e.execution_time_msc,
                    opened_at_utc=e.execution_timestamp_utc,
                )
                entry_dollar_vol = (e.volume * e.price)
                exit_dollar_vol = Decimal("0.0")
                open_lots.append(
                    EntryLot(
                        execution_id=e.id,
                        initial_volume=e.volume,
                        remaining_volume=e.volume,
                        price=e.price,
                        side=e.side,
                        commission=e.commission,
                        fee=e.fee,
                        timestamp_msc=e.execution_time_msc,
                    )
                )

            elif e.side == current_trade.side and e.entry_type == "ENTRY_IN":
                # Scale-in: add to inventory
                current_trade.total_entry_volume += e.volume
                current_trade.open_volume += e.volume
                current_trade.total_commission += e.commission
                current_trade.total_swap += e.swap
                current_trade.total_fees += e.fee
                entry_dollar_vol += (e.volume * e.price)
                current_trade.vwap_entry_price = (entry_dollar_vol / current_trade.total_entry_volume).quantize(Decimal("0.000001"))
                open_lots.append(
                    EntryLot(
                        execution_id=e.id,
                        initial_volume=e.volume,
                        remaining_volume=e.volume,
                        price=e.price,
                        side=e.side,
                        commission=e.commission,
                        fee=e.fee,
                        timestamp_msc=e.execution_time_msc,
                    )
                )

            else:
                # Reduction, Exit, or Reversal (side != current_trade.side)
                fx_rate = await InstrumentService.resolve_fx_rate(
                    session=session,
                    tenant_id=tenant_id,
                    from_currency=spec.profit_currency,
                    to_currency=account_currency,
                    timestamp_msc=e.execution_time_msc,
                )

                if e.volume <= current_trade.open_volume:
                    # Partial or exact full exit
                    current_trade.total_exit_volume += e.volume
                    current_trade.open_volume -= e.volume
                    current_trade.total_commission += e.commission
                    current_trade.total_swap += e.swap
                    current_trade.total_fees += e.fee
                    exit_dollar_vol += (e.volume * e.price)

                    chunk_maps, chunk_pnl = LotAllocationEngine.match_exit_against_lots(
                        trade_id=current_trade.id,
                        open_lots=open_lots,
                        exit_exec=e,
                        spec=spec,
                        fx_rate=fx_rate,
                    )
                    current_trade.realized_gross_pnl += chunk_pnl
                    net_maps.extend(chunk_maps)

                    if current_trade.total_exit_volume > Decimal("0.0000"):
                        current_trade.vwap_exit_price = (exit_dollar_vol / current_trade.total_exit_volume).quantize(Decimal("0.000001"))
                    current_trade.realized_net_pnl = (current_trade.realized_gross_pnl + current_trade.total_commission + current_trade.total_swap + current_trade.total_fees).quantize(Decimal("0.0001"))

                    if current_trade.open_volume == Decimal("0.0000"):
                        current_trade.trade_status = "CLOSED"
                        current_trade.closed_at_msc = e.execution_time_msc
                        current_trade.closed_at_utc = e.execution_timestamp_utc
                        current_trade.duration_seconds = max(0, int((e.execution_time_msc - current_trade.opened_at_msc) / 1000))

                        # Post ledger transaction
                        postings = DoubleEntryLedgerEngine.build_trade_settlement_postings(current_trade, account_currency)
                        tx, db_postings = DoubleEntryLedgerEngine.validate_and_create_transaction(
                            tenant_id=tenant_id,
                            reconstruction_run_id=reconstruction_run_id,
                            account_number=account_number,
                            transaction_type="TRADE_SETTLEMENT",
                            transaction_time_msc=e.execution_time_msc,
                            transaction_timestamp_utc=e.execution_timestamp_utc,
                            description=f"Netting Trade #{current_trade.position_ticket} ({current_trade.symbol} {current_trade.side}): PnL={current_trade.realized_gross_pnl}",
                            source_observation_id=e.observation_id,
                            postings=postings,
                            trade_id=current_trade.id,
                        )
                        net_txs.append(tx)
                        net_postings.extend(db_postings)

                        net_trades.append(current_trade)
                        current_trade = None
                        open_lots.clear()
                    else:
                        current_trade.trade_status = "PARTIALLY_CLOSED"

                else:
                    # REVERSAL (e.volume > current_trade.open_volume) on DEAL_ENTRY_INOUT
                    close_vol = current_trade.open_volume
                    residual_vol = e.volume - close_vol

                    current_trade.total_exit_volume += close_vol
                    current_trade.open_volume = Decimal("0.0000")
                    exit_dollar_vol += (close_vol * e.price)
                    current_trade.vwap_exit_price = (exit_dollar_vol / current_trade.total_exit_volume).quantize(Decimal("0.000001"))

                    chunk_maps, chunk_pnl = LotAllocationEngine.match_exit_against_lots(
                        trade_id=current_trade.id,
                        open_lots=open_lots,
                        exit_exec=e,
                        spec=spec,
                        fx_rate=fx_rate,
                    )
                    current_trade.realized_gross_pnl += chunk_pnl
                    net_maps.extend(chunk_maps)

                    current_trade.realized_net_pnl = (current_trade.realized_gross_pnl + current_trade.total_commission + current_trade.total_swap + current_trade.total_fees).quantize(Decimal("0.0001"))
                    current_trade.trade_status = "REVERSED"
                    current_trade.closed_at_msc = e.execution_time_msc
                    current_trade.closed_at_utc = e.execution_timestamp_utc
                    current_trade.duration_seconds = max(0, int((e.execution_time_msc - current_trade.opened_at_msc) / 1000))

                    # Post ledger transaction for reversed trade
                    postings = DoubleEntryLedgerEngine.build_trade_settlement_postings(current_trade, account_currency)
                    tx, db_postings = DoubleEntryLedgerEngine.validate_and_create_transaction(
                        tenant_id=tenant_id,
                        reconstruction_run_id=reconstruction_run_id,
                        account_number=account_number,
                        transaction_type="TRADE_SETTLEMENT",
                        transaction_time_msc=e.execution_time_msc,
                        transaction_timestamp_utc=e.execution_timestamp_utc,
                        description=f"Reversed Netting Trade #{current_trade.position_ticket} ({current_trade.symbol}): PnL={current_trade.realized_gross_pnl}",
                        source_observation_id=e.observation_id,
                        postings=postings,
                        trade_id=current_trade.id,
                    )
                    net_txs.append(tx)
                    net_postings.extend(db_postings)

                    net_trades.append(current_trade)

                    # Create NEW Trade in opposite direction with residual volume
                    new_trade_id = uuid.uuid4()
                    current_trade = CanonicalTrade(
                        id=new_trade_id,
                        tenant_id=tenant_id,
                        reconstruction_run_id=reconstruction_run_id,
                        account_number=account_number,
                        server_name=server_name,
                        symbol=symbol,
                        side=e.side,
                        account_mode="NETTING",
                        position_ticket=e.position_ticket or e.deal_ticket,
                        total_entry_volume=residual_vol,
                        total_exit_volume=Decimal("0.0000"),
                        open_volume=residual_vol,
                        vwap_entry_price=e.price,
                        vwap_exit_price=None,
                        realized_gross_pnl=Decimal("0.0000"),
                        total_commission=Decimal("0.0000"),
                        total_swap=Decimal("0.0000"),
                        total_fees=Decimal("0.0000"),
                        realized_net_pnl=Decimal("0.0000"),
                        trade_status="OPEN",
                        opened_at_msc=e.execution_time_msc,
                        opened_at_utc=e.execution_timestamp_utc,
                    )
                    entry_dollar_vol = (residual_vol * e.price)
                    exit_dollar_vol = Decimal("0.0")
                    open_lots = [
                        EntryLot(
                            execution_id=e.id,
                            initial_volume=residual_vol,
                            remaining_volume=residual_vol,
                            price=e.price,
                            side=e.side,
                            commission=Decimal("0.0000"),
                            fee=Decimal("0.0000"),
                            timestamp_msc=e.execution_time_msc,
                        )
                    ]

        if current_trade is not None and current_trade not in net_trades:
            net_trades.append(current_trade)

        return net_trades, net_maps, net_txs, net_postings

    @classmethod
    def _normalize_entry_type(cls, raw_entry: str) -> str:
        """Maps raw MT5 deal entry string/int to canonical enum."""
        if raw_entry in ("DEAL_ENTRY_IN", "0"):
            return "ENTRY_IN"
        elif raw_entry in ("DEAL_ENTRY_OUT", "1"):
            return "ENTRY_OUT"
        elif raw_entry in ("DEAL_ENTRY_INOUT", "2"):
            return "ENTRY_INOUT"
        elif raw_entry in ("DEAL_ENTRY_OUT_BY", "3"):
            return "ENTRY_OUT_BY"
        return "ENTRY_IN"

    @classmethod
    def _classify_balance_event_type(cls, deal_type: str, profit: Any) -> str:
        """Classifies MT5 balance deal type into canonical balance event category."""
        p_val = Decimal(str(profit or "0.0"))
        if deal_type in ("DEAL_TYPE_BALANCE", "2"):
            return "DEPOSIT" if p_val >= 0 else "WITHDRAWAL"
        elif deal_type in ("DEAL_TYPE_CREDIT", "3"):
            return "CREDIT"
        elif deal_type in ("DEAL_TYPE_CHARGE", "4"):
            return "FEE"
        elif deal_type in ("DEAL_TYPE_CORRECTION", "5"):
            return "CORRECTION"
        elif deal_type in ("DEAL_TYPE_BONUS", "6"):
            return "CREDIT"
        elif deal_type in ("DEAL_DIVIDEND", "DEAL_DIVIDEND_FRANKED", "15", "16"):
            return "DIVIDEND"
        elif deal_type in ("DEAL_TAX", "17"):
            return "TAX"
        return "FEE"
