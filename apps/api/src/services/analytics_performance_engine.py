"""TradeDNA Phase 7 - Performance & Drawdown Analytics Engine.
Calculates deterministic performance statistics, high-water mark drawdowns,
holding duration metrics, and streak analytics from Phase 5 Canonical Trades.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, Sequence
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.canonical_ledger import (
    CanonicalBalanceEvent,
    CanonicalLedgerPosting,
    CanonicalLedgerTransaction,
    CanonicalTrade,
)
from src.services.analytics_context import AnalyticsCalculationContext


class AnalyticsPerformanceEngine:
    """
    Computes deterministic trading performance and drawdown metrics
    over canonical closed trades and ledger transactions.
    """

    @classmethod
    def calculate_trade_metrics(
        cls,
        trades: Sequence[CanonicalTrade],
        context: AnalyticsCalculationContext,
        initial_balance: Decimal = Decimal("0.0000"),
    ) -> dict[str, Any]:
        """
        Calculates all performance, drawdown, duration, streak, and concentration
        metrics for a given sequence of canonical trades.
        """
        # Filter closed trades
        closed_trades = [t for t in trades if t.trade_status in ("CLOSED", "PARTIALLY_CLOSED") and t.closed_at_utc is not None]
        # Sort chronologically by close time (or open time as tiebreaker)
        closed_trades.sort(key=lambda t: (t.closed_at_utc or t.opened_at_utc, t.opened_at_utc))

        total_trades = len(closed_trades)
        if total_trades == 0:
            return cls._empty_metrics(context)

        winning_trades = 0
        losing_trades = 0
        breakeven_trades = 0
        gross_profit = Decimal("0.0000")
        gross_loss = Decimal("0.0000")
        net_pnl = Decimal("0.0000")

        pnl_list: list[Decimal] = []
        winner_pnl_list: list[Decimal] = []
        loser_pnl_list: list[Decimal] = []

        holding_sec_list: list[int] = []
        winner_holding_sec_list: list[int] = []
        loser_holding_sec_list: list[int] = []

        total_volume = Decimal("0.0000")
        max_lot_size = Decimal("0.0000")
        symbol_volumes: dict[str, Decimal] = {}

        # Streak trackers
        current_win_streak = 0
        max_win_streak = 0
        current_loss_streak = 0
        max_loss_streak = 0

        # Drawdown trackers
        running_balance = initial_balance
        peak_balance = initial_balance
        max_drawdown_amount = Decimal("0.0000")
        max_drawdown_pct = Decimal("0.0000")
        drawdown_duration_sec = 0
        recovery_duration_sec = 0

        current_dd_start_time: Optional[datetime] = None
        peak_time: Optional[datetime] = closed_trades[0].opened_at_utc if initial_balance > Decimal("0.0000") else None

        for t in closed_trades:
            pnl = t.realized_net_pnl.quantize(Decimal("0.0001"))
            pnl_list.append(pnl)
            net_pnl += pnl

            # Duration
            close_dt = t.closed_at_utc or t.opened_at_utc
            duration_s = max(0, int((close_dt - t.opened_at_utc).total_seconds()))
            holding_sec_list.append(duration_s)

            # Volume & Symbol
            vol = t.total_entry_volume.quantize(Decimal("0.0001"))
            total_volume += vol
            if vol > max_lot_size:
                max_lot_size = vol
            symbol_volumes[t.symbol] = symbol_volumes.get(t.symbol, Decimal("0.0000")) + vol

            # Categorization & Streaks
            if pnl > Decimal("0.0000"):
                winning_trades += 1
                gross_profit += pnl
                winner_pnl_list.append(pnl)
                winner_holding_sec_list.append(duration_s)

                current_win_streak += 1
                if current_win_streak > max_win_streak:
                    max_win_streak = current_win_streak
                current_loss_streak = 0

            elif pnl < Decimal("0.0000"):
                losing_trades += 1
                gross_loss += abs(pnl)
                loser_pnl_list.append(pnl)
                loser_holding_sec_list.append(duration_s)

                current_loss_streak += 1
                if current_loss_streak > max_loss_streak:
                    max_loss_streak = current_loss_streak
                current_win_streak = 0

            else:
                breakeven_trades += 1
                current_win_streak = 0
                current_loss_streak = 0

            # High-water mark drawdown calculation
            running_balance += pnl
            if running_balance > peak_balance or peak_time is None:
                if current_dd_start_time and peak_time:
                    rec_dur = int((close_dt - current_dd_start_time).total_seconds())
                    if rec_dur > recovery_duration_sec:
                        recovery_duration_sec = rec_dur
                peak_balance = running_balance
                peak_time = close_dt
                current_dd_start_time = None
            else:
                if not current_dd_start_time and peak_time:
                    current_dd_start_time = peak_time
                dd_amt = (peak_balance - running_balance).quantize(Decimal("0.0001"))
                if dd_amt > max_drawdown_amount:
                    max_drawdown_amount = dd_amt
                if peak_balance > Decimal("0.0000"):
                    dd_pct = (dd_amt / peak_balance).quantize(Decimal("0.0001"))
                    if dd_pct > max_drawdown_pct:
                        max_drawdown_pct = dd_pct
                if current_dd_start_time:
                    cur_dur = int((close_dt - current_dd_start_time).total_seconds())
                    if cur_dur > drawdown_duration_sec:
                        drawdown_duration_sec = cur_dur

        # Summary Rates & Averages
        win_rate = (Decimal(winning_trades) / Decimal(total_trades)).quantize(Decimal("0.0001"))
        loss_rate = (Decimal(losing_trades) / Decimal(total_trades)).quantize(Decimal("0.0001"))

        if gross_loss > Decimal("0.0000"):
            profit_factor = (gross_profit / gross_loss).quantize(Decimal("0.0001"))
        elif gross_profit > Decimal("0.0000"):
            profit_factor = Decimal("999.9900")
        else:
            profit_factor = Decimal("0.0000")

        avg_winner = (gross_profit / Decimal(max(1, winning_trades))).quantize(Decimal("0.0001"))
        avg_loser = (gross_loss / Decimal(max(1, losing_trades))).quantize(Decimal("0.0001"))

        if avg_loser > Decimal("0.0000"):
            payoff_ratio = (avg_winner / avg_loser).quantize(Decimal("0.0001"))
        elif avg_winner > Decimal("0.0000"):
            payoff_ratio = Decimal("999.9900")
        else:
            payoff_ratio = Decimal("0.0000")

        expectancy = (net_pnl / Decimal(total_trades)).quantize(Decimal("0.0001"))
        avg_trade = expectancy

        pnl_list.sort()
        median_trade = pnl_list[len(pnl_list) // 2].quantize(Decimal("0.0001"))
        largest_winner = max(pnl_list).quantize(Decimal("0.0001"))
        largest_loser = min(pnl_list).quantize(Decimal("0.0001"))

        # Recovery Factor
        if max_drawdown_amount > Decimal("0.0000"):
            recovery_factor = (net_pnl / max_drawdown_amount).quantize(Decimal("0.0001"))
        else:
            recovery_factor = Decimal("999.9900") if net_pnl > Decimal("0.0000") else Decimal("0.0000")

        # Durations
        avg_holding_sec = int(sum(holding_sec_list) / max(1, len(holding_sec_list)))
        holding_sec_list.sort()
        median_holding_sec = holding_sec_list[len(holding_sec_list) // 2]
        avg_winner_holding_sec = int(sum(winner_holding_sec_list) / max(1, len(winner_holding_sec_list)))
        avg_loser_holding_sec = int(sum(loser_holding_sec_list) / max(1, len(loser_holding_sec_list)))

        if avg_winner_holding_sec > 0:
            duration_ratio = (Decimal(avg_loser_holding_sec) / Decimal(avg_winner_holding_sec)).quantize(Decimal("0.0001"))
        else:
            duration_ratio = Decimal("1.0000")

        avg_lot_size = (total_volume / Decimal(total_trades)).quantize(Decimal("0.0001"))

        # Symbol Concentration (HHI)
        hhi_val = Decimal("0.00")
        top_symbol_volume_pct = Decimal("0.0000")
        if total_volume > Decimal("0.0000"):
            max_sym_vol = max(symbol_volumes.values())
            top_symbol_volume_pct = (max_sym_vol / total_volume).quantize(Decimal("0.0001"))
            for s_vol in symbol_volumes.values():
                share_pct = (s_vol / total_volume) * Decimal("100")
                hhi_val += share_pct * share_pct
            hhi_val = hhi_val.quantize(Decimal("0.01"))

        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "breakeven_trades": breakeven_trades,
            "win_rate": win_rate,
            "loss_rate": loss_rate,
            "gross_profit": gross_profit.quantize(Decimal("0.0001")),
            "gross_loss": gross_loss.quantize(Decimal("0.0001")),
            "net_pnl": net_pnl.quantize(Decimal("0.0001")),
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "payoff_ratio": payoff_ratio,
            "avg_trade": avg_trade,
            "median_trade": median_trade,
            "avg_winner": avg_winner,
            "avg_loser": avg_loser,
            "largest_winner": largest_winner,
            "largest_loser": largest_loser,
            "max_drawdown_amount": max_drawdown_amount,
            "max_drawdown_pct": max_drawdown_pct,
            "recovery_factor": recovery_factor,
            "drawdown_duration_sec": drawdown_duration_sec,
            "recovery_duration_sec": recovery_duration_sec,
            "avg_holding_sec": avg_holding_sec,
            "median_holding_sec": median_holding_sec,
            "avg_winner_holding_sec": avg_winner_holding_sec,
            "avg_loser_holding_sec": avg_loser_holding_sec,
            "duration_ratio": duration_ratio,
            "total_volume_lots": total_volume,
            "avg_lot_size": avg_lot_size,
            "max_lot_size": max_lot_size,
            "max_consecutive_wins": max_win_streak,
            "max_consecutive_losses": max_loss_streak,
            "hhi_symbol_concentration": hhi_val,
            "top_symbol_volume_pct": top_symbol_volume_pct,
            "currency": context.reporting_currency,
            "data_integrity_score": context.data_integrity_score,
            "integrity_grade": context.integrity_grade,
            "is_compromised": context.is_compromised,
            "calculation_version": context.calculation_engine_version,
        }

    @classmethod
    def _empty_metrics(cls, context: AnalyticsCalculationContext) -> dict[str, Any]:
        """Returns zeroed metrics for an empty trade set."""
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "breakeven_trades": 0,
            "win_rate": Decimal("0.0000"),
            "loss_rate": Decimal("0.0000"),
            "gross_profit": Decimal("0.0000"),
            "gross_loss": Decimal("0.0000"),
            "net_pnl": Decimal("0.0000"),
            "profit_factor": Decimal("0.0000"),
            "expectancy": Decimal("0.0000"),
            "payoff_ratio": Decimal("0.0000"),
            "avg_trade": Decimal("0.0000"),
            "median_trade": Decimal("0.0000"),
            "avg_winner": Decimal("0.0000"),
            "avg_loser": Decimal("0.0000"),
            "largest_winner": Decimal("0.0000"),
            "largest_loser": Decimal("0.0000"),
            "max_drawdown_amount": Decimal("0.0000"),
            "max_drawdown_pct": Decimal("0.0000"),
            "recovery_factor": Decimal("0.0000"),
            "drawdown_duration_sec": 0,
            "recovery_duration_sec": 0,
            "avg_holding_sec": 0,
            "median_holding_sec": 0,
            "avg_winner_holding_sec": 0,
            "avg_loser_holding_sec": 0,
            "duration_ratio": Decimal("0.0000"),
            "total_volume_lots": Decimal("0.0000"),
            "avg_lot_size": Decimal("0.0000"),
            "max_lot_size": Decimal("0.0000"),
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "hhi_symbol_concentration": Decimal("0.00"),
            "top_symbol_volume_pct": Decimal("0.0000"),
            "currency": context.reporting_currency,
            "data_integrity_score": context.data_integrity_score,
            "integrity_grade": context.integrity_grade,
            "is_compromised": context.is_compromised,
            "calculation_version": context.calculation_engine_version,
        }
