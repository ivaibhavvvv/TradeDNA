"""TradeDNA Phase 7 - Historical Baseline & Drift Engine.
Compares current trading performance against historical baselines
(7D vs 30D, 30D vs 90D, Month vs Historical) to detect meaningful behavioral shifts.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional, Sequence
import uuid
from src.models.canonical_ledger import CanonicalTrade
from src.services.analytics_context import AnalyticsCalculationContext
from src.services.analytics_performance_engine import AnalyticsPerformanceEngine


class AnalyticsBaselineEngine:
    """
    Computes statistical and performance comparisons between recent trading
    cohorts and established historical baselines.
    """

    COHORTS = [
        ("CURRENT_7D_VS_PREV_30D", 7, 30),
        ("CURRENT_30D_VS_PREV_90D", 30, 90),
    ]

    @classmethod
    def compute_all_baselines(
        cls,
        trades: Sequence[CanonicalTrade],
        context: AnalyticsCalculationContext,
        as_of_time: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Calculates baseline comparisons for standard time cohorts."""
        now = as_of_time or datetime.now(timezone.utc)
        results = []

        closed_trades = [t for t in trades if t.trade_status in ("CLOSED", "PARTIALLY_CLOSED") and t.closed_at_utc is not None]

        for cohort_name, curr_days, base_days in cls.COHORTS:
            curr_start = now - timedelta(days=curr_days)
            base_start = now - timedelta(days=base_days)

            curr_trades = [t for t in closed_trades if curr_start <= (t.closed_at_utc or t.opened_at_utc) <= now]
            base_trades = [t for t in closed_trades if base_start <= (t.closed_at_utc or t.opened_at_utc) < curr_start]

            # If no historical baseline trades exist, compare against all trades before curr_start
            if not base_trades:
                base_trades = [t for t in closed_trades if (t.closed_at_utc or t.opened_at_utc) < curr_start]

            comp = cls._compare_periods(
                curr_trades=curr_trades,
                base_trades=base_trades,
                cohort_name=cohort_name,
                curr_start=curr_start,
                curr_end=now,
                base_start=base_start,
                base_end=curr_start,
                context=context,
            )
            results.append(comp)

        return results

    @classmethod
    def _compare_periods(
        cls,
        curr_trades: list[CanonicalTrade],
        base_trades: list[CanonicalTrade],
        cohort_name: str,
        curr_start: datetime,
        curr_end: datetime,
        base_start: datetime,
        base_end: datetime,
        context: AnalyticsCalculationContext,
    ) -> dict[str, Any]:
        """Calculates metric deltas and detects meaningful behavioral drifts."""
        curr_perf = AnalyticsPerformanceEngine.calculate_trade_metrics(curr_trades, context)
        base_perf = AnalyticsPerformanceEngine.calculate_trade_metrics(base_trades, context)

        metrics_map = {}
        drifts: list[dict[str, Any]] = []

        # 1. Win Rate Drift
        wr_curr = curr_perf["win_rate"]
        wr_base = base_perf["win_rate"]
        wr_delta = wr_curr - wr_base
        metrics_map["win_rate"] = {
            "current": str(wr_curr),
            "baseline": str(wr_base),
            "delta": str(wr_delta),
        }
        if abs(wr_delta) >= Decimal("0.1500") and base_perf["total_trades"] >= 5:
            drifts.append({
                "metric": "WIN_RATE",
                "severity": "HIGH" if wr_delta < 0 else "INFO",
                "message": f"Win rate shifted by {wr_delta * 100:+.1f}% (from {wr_base * 100:.1f}% to {wr_curr * 100:.1f}%)",
                "drift_type": "DEGRADATION" if wr_delta < 0 else "IMPROVEMENT",
            })

        # 2. Profit Factor Drift
        pf_curr = curr_perf["profit_factor"]
        pf_base = base_perf["profit_factor"]
        pf_delta = pf_curr - pf_base
        metrics_map["profit_factor"] = {
            "current": str(pf_curr),
            "baseline": str(pf_base),
            "delta": str(pf_delta),
        }
        if pf_base > Decimal("0.0000") and abs(pf_delta / pf_base) >= Decimal("0.2500"):
            drifts.append({
                "metric": "PROFIT_FACTOR",
                "severity": "HIGH" if pf_delta < 0 else "INFO",
                "message": f"Profit factor changed from {pf_base:.2f} to {pf_curr:.2f}",
                "drift_type": "DEGRADATION" if pf_delta < 0 else "IMPROVEMENT",
            })

        # 3. Position Size Expansion / Contraction
        lot_curr = curr_perf["avg_lot_size"]
        lot_base = base_perf["avg_lot_size"]
        metrics_map["avg_lot_size"] = {
            "current": str(lot_curr),
            "baseline": str(lot_base),
            "delta": str(lot_curr - lot_base),
        }
        if lot_base > Decimal("0.0000"):
            lot_pct_change = (lot_curr - lot_base) / lot_base
            if lot_pct_change >= Decimal("0.5000"):
                drifts.append({
                    "metric": "POSITION_SIZING",
                    "severity": "HIGH",
                    "message": f"Average lot size expanded by {lot_pct_change * 100:+.1f}% vs baseline",
                    "drift_type": "HIGH_RISK_SHIFT",
                })

        # 4. Holding Duration Drift
        dur_curr = curr_perf["avg_holding_sec"]
        dur_base = base_perf["avg_holding_sec"]
        metrics_map["avg_holding_sec"] = {
            "current": dur_curr,
            "baseline": dur_base,
            "delta": dur_curr - dur_base,
        }

        # Determine overall trajectory
        degradations = sum(1 for d in drifts if d["drift_type"] in ("DEGRADATION", "HIGH_RISK_SHIFT"))
        improvements = sum(1 for d in drifts if d["drift_type"] == "IMPROVEMENT")

        if degradations >= 2 or any(d["drift_type"] == "HIGH_RISK_SHIFT" for d in drifts):
            trajectory = "HIGH_RISK_SHIFT" if any(d["drift_type"] == "HIGH_RISK_SHIFT" for d in drifts) else "DEGRADING"
        elif improvements > degradations:
            trajectory = "IMPROVING"
        else:
            trajectory = "STABLE"

        return {
            "tenant_id": context.tenant_id,
            "broker": context.broker,
            "account_number": context.account_number,
            "server_name": context.server_name,
            "reconstruction_run_id": context.reconstruction_run_id,
            "comparison_cohort": cohort_name,
            "current_start_utc": curr_start,
            "current_end_utc": curr_end,
            "baseline_start_utc": base_start,
            "baseline_end_utc": base_end,
            "metric_comparisons": metrics_map,
            "detected_drifts": drifts,
            "overall_trajectory": trajectory,
            "calculation_version": context.calculation_engine_version,
        }
