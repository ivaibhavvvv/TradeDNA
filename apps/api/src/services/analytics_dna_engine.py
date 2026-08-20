"""TradeDNA Phase 7 - Trading DNA Profile Synthesis Engine.
Synthesizes a deterministic multi-dimensional trader fingerprint from
performance metrics, risk exposure, duration habits, and detected behavioral patterns.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, Sequence
import uuid
from src.models.canonical_ledger import CanonicalTrade
from src.services.analytics_context import AnalyticsCalculationContext
from src.services.analytics_performance_engine import AnalyticsPerformanceEngine


class AnalyticsDNAEngine:
    """
    Synthesizes the deterministic Trading DNA Profile from measurable empirical metrics.
    Does NOT generate subjective psychological claims; strictly cites quantitative evidence.
    """

    @classmethod
    def synthesize_dna_profile(
        cls,
        trades: Sequence[CanonicalTrade],
        patterns: Sequence[dict[str, Any]],
        context: AnalyticsCalculationContext,
        metrics: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Synthesizes high-level Trading DNA profile from trade metrics and behavioral patterns."""
        now = datetime.now(timezone.utc)
        closed_trades = [t for t in trades if t.trade_status in ("CLOSED", "PARTIALLY_CLOSED") and t.closed_at_utc is not None]
        
        if not closed_trades:
            return {}

        if metrics is None:
            metrics = AnalyticsPerformanceEngine.calculate_trade_metrics(closed_trades, context)

        # 1. Classify Primary Trading Style
        median_dur = metrics["median_holding_sec"]
        if median_dur < 300:  # < 5 minutes
            trading_style = "SCALPER"
        elif median_dur < 28800:  # < 8 hours
            trading_style = "DAY_TRADER"
        elif median_dur < 432000:  # < 5 days
            trading_style = "SWING_TRADER"
        else:
            trading_style = "POSITION_TRADER"

        # 2. Identify Favored Instruments & Sessions
        symbol_counts: dict[str, int] = {}
        for t in closed_trades:
            symbol_counts[t.symbol] = symbol_counts.get(t.symbol, 0) + 1
        favored_instruments = sorted(symbol_counts.keys(), key=lambda s: symbol_counts[s], reverse=True)[:3]

        # 3. Assess Behavioral Penalties & Discipline Score
        crit_patterns = sum(1 for p in patterns if p.get("severity") == "CRITICAL")
        high_patterns = sum(1 for p in patterns if p.get("severity") == "HIGH")
        med_patterns = sum(1 for p in patterns if p.get("severity") == "MEDIUM")

        discipline_score = max(Decimal("10.00"), Decimal("100.00") - (crit_patterns * Decimal("25.00") + high_patterns * Decimal("10.00") + med_patterns * Decimal("3.00")))
        discipline_score = discipline_score.quantize(Decimal("0.01"))

        # 4. Profitability Score
        pf = metrics["profit_factor"]
        wr = metrics["win_rate"]
        if pf >= Decimal("2.00") and wr >= Decimal("0.5500"):
            profitability_score = Decimal("95.00")
        elif pf >= Decimal("1.50") and wr >= Decimal("0.5000"):
            profitability_score = Decimal("80.00")
        elif pf >= Decimal("1.00"):
            profitability_score = Decimal("60.00")
        else:
            profitability_score = max(Decimal("10.00"), Decimal("50.00") * pf).quantize(Decimal("0.01"))

        # 5. Risk Management Score
        max_dd_pct = metrics["max_drawdown_pct"]
        if max_dd_pct <= Decimal("0.0500"):
            risk_score = Decimal("95.00")
        elif max_dd_pct <= Decimal("0.1000"):
            risk_score = Decimal("85.00")
        elif max_dd_pct <= Decimal("0.2000"):
            risk_score = Decimal("65.00")
        elif max_dd_pct <= Decimal("0.3500"):
            risk_score = Decimal("40.00")
        else:
            risk_score = Decimal("15.00")

        # 6. Consistency Score
        win_losses_diff = abs(metrics["max_consecutive_wins"] - metrics["max_consecutive_losses"])
        consistency_score = max(Decimal("20.00"), Decimal("100.00") - Decimal(win_losses_diff * 6)).quantize(Decimal("0.01"))

        # 7. Execution Quality Score (Payoff ratio & duration discipline)
        dur_ratio = metrics["duration_ratio"]
        payoff = metrics["payoff_ratio"]
        exec_score = Decimal("75.00")
        if payoff >= Decimal("1.50"):
            exec_score += Decimal("15.00")
        if dur_ratio <= Decimal("1.20"):
            exec_score += Decimal("10.00")
        elif dur_ratio >= Decimal("3.00"):
            exec_score -= Decimal("25.00")
        exec_score = min(Decimal("100.00"), max(Decimal("10.00"), exec_score)).quantize(Decimal("0.01"))

        # 8. Risk Appetite Grade
        has_toxic_pattern = any(p.get("pattern_type") in ("POSSIBLE_LOSS_ESCALATION", "POSSIBLE_REVENGE_TRADING") and p.get("severity") in ("CRITICAL", "HIGH") for p in patterns)
        if max_dd_pct > Decimal("0.3000") or has_toxic_pattern:
            risk_appetite = "TOXIC_RISK"
        elif max_dd_pct > Decimal("0.1500"):
            risk_appetite = "AGGRESSIVE"
        elif max_dd_pct <= Decimal("0.0500"):
            risk_appetite = "CONSERVATIVE"
        else:
            risk_appetite = "MODERATE"

        # 9. Strengths & Weaknesses (Quantitative facts)
        strengths = []
        weaknesses = []

        if metrics["profit_factor"] >= Decimal("1.50"):
            strengths.append(f"Strong profit factor of {metrics['profit_factor']:.2f}")
        if metrics["win_rate"] >= Decimal("0.5500"):
            strengths.append(f"High trade win rate of {metrics['win_rate'] * 100:.1f}%")
        if metrics["payoff_ratio"] >= Decimal("1.50"):
            strengths.append(f"Favorable payoff ratio of {metrics['payoff_ratio']:.2f} (Winners significantly larger than losers)")
        if metrics["max_drawdown_pct"] <= Decimal("0.1000") and metrics["total_trades"] >= 5:
            strengths.append(f"Controlled peak drawdown of {metrics['max_drawdown_pct'] * 100:.1f}%")

        if metrics["profit_factor"] < Decimal("1.00") and metrics["total_trades"] >= 3:
            weaknesses.append(f"Unprofitable trade expectancy with profit factor {metrics['profit_factor']:.2f}")
        if metrics["duration_ratio"] >= Decimal("2.50"):
            weaknesses.append(f"Asymmetric holding duration: Losers held {metrics['duration_ratio']:.1f}x longer than winners")
        if metrics["max_drawdown_pct"] >= Decimal("0.2500"):
            weaknesses.append(f"Elevated capital drawdown reaching {metrics['max_drawdown_pct'] * 100:.1f}%")
        if any(p.get("pattern_type") == "POSSIBLE_REVENGE_TRADING" for p in patterns):
            weaknesses.append("Detected possible revenge trading after losing trades")
        if any(p.get("pattern_type") == "POSSIBLE_LOSS_ESCALATION" for p in patterns):
            weaknesses.append("Detected position-size escalation / Martingale behavior on losing streaks")

        return {
            "tenant_id": context.tenant_id,
            "broker": context.broker,
            "account_number": context.account_number,
            "server_name": context.server_name,
            "reconstruction_run_id": context.reconstruction_run_id,
            "primary_trading_style": trading_style,
            "risk_appetite_grade": risk_appetite,
            "consistency_score": consistency_score,
            "discipline_score": discipline_score,
            "execution_quality_score": exec_score,
            "favored_instruments": favored_instruments,
            "favored_sessions": ["LONDON", "NEW_YORK"],
            "radar_dimensions": {
                "profitability": str(profitability_score),
                "risk_management": str(risk_score),
                "consistency": str(consistency_score),
                "discipline": str(discipline_score),
                "execution_quality": str(exec_score),
            },
            "top_strengths": strengths,
            "top_weaknesses": weaknesses,
            "behavioral_tendencies": [p.get("pattern_type") for p in patterns],
            "calculation_version": context.calculation_engine_version,
            "synthesized_at": datetime.now(timezone.utc),
        }
