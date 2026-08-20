"""TradeDNA Phase 5 - Lot Allocation Engine
Performs deterministic FIFO execution inventory matching, lot-by-lot cost basis tracking,
and exact financial calculation using instrument specifications and exchange rates.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
import uuid
from src.models.canonical_ledger import CanonicalExecution, CanonicalTradeExecutionMap
from src.models.instrument_spec import InstrumentSpecification


@dataclass
class EntryLot:
    """In-memory representation of an open entry lot execution available for matching."""
    execution_id: uuid.UUID
    initial_volume: Decimal
    remaining_volume: Decimal
    price: Decimal
    side: str  # BUY, SELL
    commission: Decimal
    fee: Decimal
    timestamp_msc: int


@dataclass
class MatchResultChunk:
    """Result of a single entry lot execution matched against an exit execution."""
    entry_execution_id: uuid.UUID
    exit_execution_id: uuid.UUID
    matched_volume: Decimal
    entry_price: Decimal
    exit_price: Decimal
    realized_gross_pnl: Decimal
    attributed_commission: Decimal
    attributed_swap: Decimal
    attributed_fee: Decimal


class LotAllocationEngine:
    """Deterministic lot-by-lot FIFO matching engine for trades and positions."""

    @classmethod
    def calculate_gross_pnl(
        cls,
        side: str,  # BUY (Long) or SELL (Short)
        entry_price: Decimal,
        exit_price: Decimal,
        matched_volume: Decimal,
        spec: InstrumentSpecification,
        fx_rate: Decimal = Decimal("1.000000"),
    ) -> Decimal:
        """Calculates exact gross P&L for a matched execution chunk.
        
        Long (BUY entry, SELL exit): matched_vol * contract_size * (exit_price - entry_price) * fx_rate
        Short (SELL entry, BUY exit): matched_vol * contract_size * (entry_price - exit_price) * fx_rate
        """
        contract_size = spec.contract_size

        if side.upper() == "BUY":
            price_delta = exit_price - entry_price
        else:  # SELL (Short)
            price_delta = entry_price - exit_price

        raw_pnl = matched_volume * contract_size * price_delta
        return (raw_pnl * fx_rate).quantize(Decimal("0.0001"))

    @classmethod
    def match_exit_against_lots(
        cls,
        trade_id: uuid.UUID,
        open_lots: list[EntryLot],
        exit_exec: CanonicalExecution,
        spec: InstrumentSpecification,
        fx_rate: Decimal = Decimal("1.000000"),
    ) -> tuple[list[CanonicalTradeExecutionMap], Decimal]:
        """Matches an exit execution against the FIFO queue of open entry lots.
        Returns a list of CanonicalTradeExecutionMap records and total matched gross P&L.
        """
        match_maps: list[CanonicalTradeExecutionMap] = []
        total_pnl = Decimal("0.0000")
        exit_vol_remaining = exit_exec.volume

        # Allocate proportional swap & commission from exit fill
        total_exit_vol = exit_exec.volume

        while exit_vol_remaining > Decimal("0.0000") and open_lots:
            lot = open_lots[0]
            matched_chunk_vol = min(lot.remaining_volume, exit_vol_remaining)

            chunk_pnl = cls.calculate_gross_pnl(
                side=lot.side,
                entry_price=lot.price,
                exit_price=exit_exec.price,
                matched_volume=matched_chunk_vol,
                spec=spec,
                fx_rate=fx_rate,
            )
            total_pnl += chunk_pnl

            # Proportional fees/swaps
            vol_ratio = (matched_chunk_vol / total_exit_vol) if total_exit_vol > 0 else Decimal("0.0")
            attr_comm = (exit_exec.commission * vol_ratio).quantize(Decimal("0.0001"))
            attr_swap = (exit_exec.swap * vol_ratio).quantize(Decimal("0.0001"))
            attr_fee = (exit_exec.fee * vol_ratio).quantize(Decimal("0.0001"))

            map_record = CanonicalTradeExecutionMap(
                id=uuid.uuid4(),
                trade_id=trade_id,
                entry_execution_id=lot.execution_id,
                exit_execution_id=exit_exec.id,
                matched_volume=matched_chunk_vol,
                entry_price=lot.price,
                exit_price=exit_exec.price,
                realized_gross_pnl=chunk_pnl,
                attributed_commission=attr_comm,
                attributed_swap=attr_swap,
                attributed_fee=attr_fee,
            )
            match_maps.append(map_record)

            lot.remaining_volume -= matched_chunk_vol
            exit_vol_remaining -= matched_chunk_vol

            if lot.remaining_volume <= Decimal("0.0000"):
                open_lots.pop(0)

        exit_exec.matched_volume = total_exit_vol - exit_vol_remaining
        return match_maps, total_pnl
