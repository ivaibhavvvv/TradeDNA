"""TradeDNA Phase 7 - Behavior, Session & Symbol Feature Store Engine.
Slices canonical trades into dimensional cubes across SYMBOL, SESSION,
DAY_OF_WEEK, HOUR_OF_DAY, and DIRECTION for granular behavioral intelligence.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Sequence
import uuid
from src.models.canonical_ledger import CanonicalTrade
from src.services.analytics_context import AnalyticsCalculationContext


class AnalyticsBehaviorEngine:
    """
    Computes dimensional feature aggregates across symbols, sessions,
    and temporal buckets for storage in analytics_feature_store.
    """

    # Configurable session definitions in UTC (start_hour, end_hour)
    SESSION_DEFINITIONS = {
        "ASIAN": (0, 8),
        "LONDON": (8, 16),
        "NEW_YORK": (13, 21),
        "LONDON_NY_OVERLAP": (13, 16),
    }

    DAY_NAMES = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]

    @classmethod
    def get_trade_sessions(cls, dt: datetime) -> list[str]:
        """Returns the trading sessions active at a given UTC timestamp."""
        hour = dt.hour
        sessions = []
        for name, (start_h, end_h) in cls.SESSION_DEFINITIONS.items():
            if start_h <= hour < end_h:
                sessions.append(name)
        if not sessions:
            sessions.append("OFF_HOURS")
        return sessions

    @classmethod
    def compute_feature_cubes(
        cls,
        trades: Sequence[CanonicalTrade],
        context: AnalyticsCalculationContext,
    ) -> list[dict[str, Any]]:
        """
        Computes pre-aggregated dimensional records for all traded symbols,
        sessions, days of week, hours of day, and trade directions.
        """
        closed_trades = [t for t in trades if t.trade_status in ("CLOSED", "PARTIALLY_CLOSED") and t.closed_at_utc is not None]

        # Buckets: (dimension_type, dimension_key) -> list of trades
        cubes: dict[tuple[str, str], list[CanonicalTrade]] = {}

        for t in closed_trades:
            # 1. Symbol dimension
            sym_key = ("SYMBOL", t.symbol.upper())
            cubes.setdefault(sym_key, []).append(t)

            # 2. Direction dimension
            dir_key = ("DIRECTION", t.side.upper())
            cubes.setdefault(dir_key, []).append(t)

            # 3. Session dimensions (based on open timestamp)
            open_dt = t.opened_at_utc
            active_sessions = cls.get_trade_sessions(open_dt)
            for sess in active_sessions:
                sess_key = ("SESSION", sess)
                cubes.setdefault(sess_key, []).append(t)

            # 4. Day of Week dimension
            day_name = cls.DAY_NAMES[open_dt.weekday()]
            day_key = ("DAY_OF_WEEK", day_name)
            cubes.setdefault(day_key, []).append(t)

            # 5. Hour of Day dimension
            hour_str = f"{open_dt.hour:02d}:00"
            hour_key = ("HOUR_OF_DAY", hour_str)
            cubes.setdefault(hour_key, []).append(t)

        # Calculate metrics for each cube
        results: list[dict[str, Any]] = []
        for (dim_type, dim_key), trade_subset in cubes.items():
            cube_metrics = cls._calculate_cube_metrics(trade_subset, dim_type, dim_key, context)
            results.append(cube_metrics)

        return results

    @classmethod
    def _calculate_cube_metrics(
        cls,
        trades: list[CanonicalTrade],
        dimension_type: str,
        dimension_key: str,
        context: AnalyticsCalculationContext,
    ) -> dict[str, Any]:
        """Calculates aggregate metrics for an individual dimensional slice."""
        trade_count = len(trades)
        win_count = 0
        loss_count = 0
        gross_profit = Decimal("0.0000")
        gross_loss = Decimal("0.0000")
        net_pnl = Decimal("0.0000")
        total_vol = Decimal("0.0000")
        total_duration_sec = 0

        for t in trades:
            pnl = t.realized_net_pnl.quantize(Decimal("0.0001"))
            vol = t.total_entry_volume.quantize(Decimal("0.0001"))
            close_dt = t.closed_at_utc or t.opened_at_utc
            dur = max(0, int((close_dt - t.opened_at_utc).total_seconds()))

            net_pnl += pnl
            total_vol += vol
            total_duration_sec += dur

            if pnl > Decimal("0.0000"):
                win_count += 1
                gross_profit += pnl
            elif pnl < Decimal("0.0000"):
                loss_count += 1
                gross_loss += abs(pnl)

        win_rate = (Decimal(win_count) / Decimal(max(1, trade_count))).quantize(Decimal("0.0001"))
        if gross_loss > Decimal("0.0000"):
            profit_factor = (gross_profit / gross_loss).quantize(Decimal("0.0001"))
        elif gross_profit > Decimal("0.0000"):
            profit_factor = Decimal("999.9900")
        else:
            profit_factor = Decimal("0.0000")

        expectancy = (net_pnl / Decimal(max(1, trade_count))).quantize(Decimal("0.0001"))
        avg_holding_sec = int(total_duration_sec / max(1, trade_count))

        return {
            "tenant_id": context.tenant_id,
            "broker": context.broker,
            "account_number": context.account_number,
            "server_name": context.server_name,
            "reconstruction_run_id": context.reconstruction_run_id,
            "dimension_type": dimension_type,
            "dimension_key": dimension_key,
            "trade_count": trade_count,
            "win_count": win_count,
            "loss_count": loss_count,
            "volume_lots": total_vol,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "net_pnl": net_pnl,
            "profit_factor": profit_factor,
            "win_rate": win_rate,
            "expectancy": expectancy,
            "avg_holding_sec": avg_holding_sec,
            "features_json": {
                "avg_lot_size": str((total_vol / Decimal(max(1, trade_count))).quantize(Decimal("0.0001"))),
                "breakeven_count": trade_count - win_count - loss_count,
            },
            "calculation_version": context.calculation_engine_version,
        }
