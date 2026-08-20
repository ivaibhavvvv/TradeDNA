"""TradeDNA Phase 7 - Deterministic Behavioral Pattern Engine.
Executes rule-based algorithms to detect behavioral trading anomalies
(Possible revenge trading, overtrading spikes, loss escalation, loser holding,
winner cutting, session deterioration, rapid re-entry, and drawdown acceleration).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional, Sequence
import uuid
from src.models.canonical_ledger import CanonicalTrade
from src.services.analytics_context import AnalyticsCalculationContext

PATTERN_RULE_VERSION = "1.0.0"


class AnalyticsPatternEngine:
    """
    Deterministic rule-based detector for trading behavior patterns and anomalies.
    Does NOT use LLMs or subjective judgments; strictly evaluates objective quantitative criteria.
    """

    @classmethod
    def detect_all_patterns(
        cls,
        trades: Sequence[CanonicalTrade],
        context: AnalyticsCalculationContext,
        initial_balance: Decimal = Decimal("10000.0000"),
    ) -> list[dict[str, Any]]:
        """Runs all deterministic pattern detectors across the canonical trade sequence."""
        closed_trades = [t for t in trades if t.trade_status in ("CLOSED", "PARTIALLY_CLOSED") and t.closed_at_utc is not None]
        closed_trades.sort(key=lambda t: (t.closed_at_utc or t.opened_at_utc, t.opened_at_utc))

        if len(closed_trades) < 2:
            return []

        patterns: list[dict[str, Any]] = []

        # 1. Revenge Trading Detector
        patterns.extend(cls._detect_revenge_trading(closed_trades, context))

        # 2. Overtrading Spike Detector
        patterns.extend(cls._detect_overtrading_spikes(closed_trades, context))

        # 3. Loss Escalation / Martingale Detector
        patterns.extend(cls._detect_loss_escalation(closed_trades, context))

        # 4. Loser Holding vs Winner Cutting Detectors
        patterns.extend(cls._detect_duration_asymmetries(closed_trades, context))

        # 5. Rapid Re-Entry Detector
        patterns.extend(cls._detect_rapid_reentry(closed_trades, context))

        # 6. Session Deterioration Detector
        patterns.extend(cls._detect_session_deterioration(closed_trades, context))

        # 7. Drawdown Acceleration Detector
        patterns.extend(cls._detect_drawdown_acceleration(closed_trades, context, initial_balance))

        return patterns

    @classmethod
    def _detect_revenge_trading(
        cls,
        trades: list[CanonicalTrade],
        context: AnalyticsCalculationContext,
    ) -> list[dict[str, Any]]:
        """
        Detects possible revenge trading: entering a trade within <= 180s after a loss
        with volume >= 1.5x of the losing trade or opposite side on the same symbol.
        """
        results = []
        for i in range(len(trades) - 1):
            t_prior = trades[i]
            t_next = trades[i + 1]

            if t_prior.realized_net_pnl < Decimal("0.0000"):
                close_dt = t_prior.closed_at_utc or t_prior.opened_at_utc
                open_dt = t_next.opened_at_utc

                inter_seconds = int((open_dt - close_dt).total_seconds())
                if 0 <= inter_seconds <= 180:
                    vol_prior = t_prior.total_entry_volume
                    vol_next = t_next.total_entry_volume

                    vol_ratio = (vol_next / max(Decimal("0.0001"), vol_prior)).quantize(Decimal("0.01"))
                    is_scaled_up = vol_ratio >= Decimal("1.50")
                    is_flipped_direction = (t_prior.symbol == t_next.symbol and t_prior.side != t_next.side)

                    if is_scaled_up or is_flipped_direction:
                        severity = "CRITICAL" if vol_ratio >= Decimal("2.00") else "HIGH"
                        results.append({
                            "tenant_id": context.tenant_id,
                            "broker": context.broker,
                            "account_number": context.account_number,
                            "server_name": context.server_name,
                            "reconstruction_run_id": context.reconstruction_run_id,
                            "pattern_type": "POSSIBLE_REVENGE_TRADING",
                            "detection_rule_version": PATTERN_RULE_VERSION,
                            "detection_status": "RULE_MATCHED",
                            "severity": severity,
                            "evidence_strength": "STRONG" if vol_ratio >= Decimal("2.00") else "MODERATE",
                            "window_start_utc": close_dt,
                            "window_end_utc": t_next.closed_at_utc or open_dt,
                            "supporting_trade_ids": [str(t_prior.id), str(t_next.id)],
                            "evidence_payload": {
                                "prior_trade_loss": str(t_prior.realized_net_pnl),
                                "inter_trade_seconds": inter_seconds,
                                "prior_volume": str(vol_prior),
                                "escalated_volume": str(vol_next),
                                "volume_escalation_ratio": str(vol_ratio),
                                "same_symbol_flip": is_flipped_direction,
                            },
                            "affected_metrics": {
                                "realized_net_pnl": str(t_prior.realized_net_pnl + t_next.realized_net_pnl),
                                "risk_escalation": str(vol_ratio),
                            },
                            "status": "DETECTED",
                        })
        return results

    @classmethod
    def _detect_overtrading_spikes(
        cls,
        trades: list[CanonicalTrade],
        context: AnalyticsCalculationContext,
    ) -> list[dict[str, Any]]:
        """
        Detects possible overtrading spikes: hourly trade count >= 4.0x average
        with at least 6 trades in the rolling 1-hour window.
        """
        if len(trades) < 6:
            return []

        results = []
        # Calculate baseline hourly average
        first_open = trades[0].opened_at_utc
        last_close = trades[-1].closed_at_utc or trades[-1].opened_at_utc
        total_hours = max(1.0, (last_close - first_open).total_seconds() / 3600.0)
        baseline_hourly_avg = len(trades) / total_hours

        # Slide a 1-hour window using O(N) two-pointer technique
        window_delta = timedelta(hours=1)
        n = len(trades)
        right = 0
        last_flagged_end: Optional[datetime] = None

        for left in range(n):
            t_left = trades[left]
            w_start = t_left.opened_at_utc
            if last_flagged_end and w_start < last_flagged_end:
                continue
            w_end = w_start + window_delta

            if right < left:
                right = left
            while right < n and trades[right].opened_at_utc <= w_end:
                right += 1

            w_count = right - left
            if w_count >= 6 and (w_count >= 4.0 * max(0.5, baseline_hourly_avg)):
                window_trades = trades[left:right]
                trade_ids = [str(t.id) for t in window_trades]
                last_flagged_end = w_end
                results.append({
                    "tenant_id": context.tenant_id,
                    "broker": context.broker,
                    "account_number": context.account_number,
                    "server_name": context.server_name,
                    "reconstruction_run_id": context.reconstruction_run_id,
                    "pattern_type": "POSSIBLE_OVERTRADING_SPIKE",
                    "detection_rule_version": PATTERN_RULE_VERSION,
                    "detection_status": "RULE_MATCHED",
                    "severity": "HIGH" if w_count >= 10 else "MEDIUM",
                    "evidence_strength": "STRONG",
                    "window_start_utc": w_start,
                    "window_end_utc": w_end,
                    "supporting_trade_ids": trade_ids,
                    "evidence_payload": {
                        "window_trade_count": w_count,
                        "baseline_hourly_avg": f"{baseline_hourly_avg:.2f}",
                        "surge_multiplier": f"{w_count / max(0.1, baseline_hourly_avg):.2f}",
                    },
                    "affected_metrics": {
                        "trade_frequency_hourly": w_count,
                        "window_net_pnl": str(sum(t.realized_net_pnl for t in window_trades)),
                    },
                    "status": "DETECTED",
                })
        return results

    @classmethod
    def _detect_loss_escalation(
        cls,
        trades: list[CanonicalTrade],
        context: AnalyticsCalculationContext,
    ) -> list[dict[str, Any]]:
        """
        Detects possible loss escalation / Martingale sizing:
        position size increases across >= 3 consecutive losing trades.
        """
        results = []
        losing_streak: list[CanonicalTrade] = []

        for t in trades:
            if t.realized_net_pnl < Decimal("0.0000"):
                losing_streak.append(t)
            else:
                if len(losing_streak) >= 3:
                    # Check if volume escalated monotonically
                    vols = [item.total_entry_volume for item in losing_streak]
                    is_escalating = all(vols[k] > vols[k - 1] for k in range(1, len(vols)))
                    if is_escalating:
                        cum_loss = sum(item.realized_net_pnl for item in losing_streak)
                        results.append({
                            "tenant_id": context.tenant_id,
                            "broker": context.broker,
                            "account_number": context.account_number,
                            "server_name": context.server_name,
                            "reconstruction_run_id": context.reconstruction_run_id,
                            "pattern_type": "POSSIBLE_LOSS_ESCALATION",
                            "detection_rule_version": PATTERN_RULE_VERSION,
                            "detection_status": "RULE_MATCHED",
                            "severity": "CRITICAL" if len(losing_streak) >= 4 else "HIGH",
                            "evidence_strength": "STRONG",
                            "window_start_utc": losing_streak[0].opened_at_utc,
                            "window_end_utc": losing_streak[-1].closed_at_utc or losing_streak[-1].opened_at_utc,
                            "supporting_trade_ids": [str(item.id) for item in losing_streak],
                            "evidence_payload": {
                                "consecutive_losing_trades": len(losing_streak),
                                "initial_volume": str(vols[0]),
                                "final_volume": str(vols[-1]),
                                "volume_expansion_ratio": str((vols[-1] / vols[0]).quantize(Decimal("0.01"))),
                                "cumulative_streak_loss": str(cum_loss),
                            },
                            "affected_metrics": {
                                "cumulative_loss": str(cum_loss),
                                "max_consecutive_losses": len(losing_streak),
                            },
                            "status": "DETECTED",
                        })
                losing_streak = []

        # Check trailing streak
        if len(losing_streak) >= 3:
            vols = [item.total_entry_volume for item in losing_streak]
            if all(vols[k] > vols[k - 1] for k in range(1, len(vols))):
                cum_loss = sum(item.realized_net_pnl for item in losing_streak)
                results.append({
                    "tenant_id": context.tenant_id,
                    "broker": context.broker,
                    "account_number": context.account_number,
                    "server_name": context.server_name,
                    "reconstruction_run_id": context.reconstruction_run_id,
                    "pattern_type": "POSSIBLE_LOSS_ESCALATION",
                    "detection_rule_version": PATTERN_RULE_VERSION,
                    "detection_status": "RULE_MATCHED",
                    "severity": "CRITICAL",
                    "evidence_strength": "STRONG",
                    "window_start_utc": losing_streak[0].opened_at_utc,
                    "window_end_utc": losing_streak[-1].closed_at_utc or losing_streak[-1].opened_at_utc,
                    "supporting_trade_ids": [str(item.id) for item in losing_streak],
                    "evidence_payload": {
                        "consecutive_losing_trades": len(losing_streak),
                        "initial_volume": str(vols[0]),
                        "final_volume": str(vols[-1]),
                        "cumulative_streak_loss": str(cum_loss),
                    },
                    "affected_metrics": {
                        "cumulative_loss": str(cum_loss),
                    },
                    "status": "DETECTED",
                })
        return results

    @classmethod
    def _detect_duration_asymmetries(
        cls,
        trades: list[CanonicalTrade],
        context: AnalyticsCalculationContext,
    ) -> list[dict[str, Any]]:
        """
        Detects Loser Holding (disposition effect) and Winner Cutting patterns.
        """
        results = []
        winners = [t for t in trades if t.realized_net_pnl > Decimal("0.0000")]
        losers = [t for t in trades if t.realized_net_pnl < Decimal("0.0000")]

        if len(winners) >= 3 and len(losers) >= 2:
            win_durations = [max(0, int(((t.closed_at_utc or t.opened_at_utc) - t.opened_at_utc).total_seconds())) for t in winners]
            win_durations.sort()
            median_win_sec = win_durations[len(win_durations) // 2]
            avg_win_pnl = sum(t.realized_net_pnl for t in winners) / Decimal(len(winners))

            # 1. Loser Holding Detector
            if median_win_sec > 0:
                for l in losers:
                    l_close = l.closed_at_utc or l.opened_at_utc
                    l_dur = max(0, int((l_close - l.opened_at_utc).total_seconds()))
                    if l_dur >= 3.5 * median_win_sec:
                        mult = round(l_dur / median_win_sec, 2)
                        results.append({
                            "tenant_id": context.tenant_id,
                            "broker": context.broker,
                            "account_number": context.account_number,
                            "server_name": context.server_name,
                            "reconstruction_run_id": context.reconstruction_run_id,
                            "pattern_type": "POSSIBLE_LOSER_HOLDING",
                            "detection_rule_version": PATTERN_RULE_VERSION,
                            "detection_status": "RULE_MATCHED",
                            "severity": "HIGH" if mult >= 8.0 else "MEDIUM",
                            "evidence_strength": "STRONG",
                            "window_start_utc": l.opened_at_utc,
                            "window_end_utc": l_close,
                            "supporting_trade_ids": [str(l.id)],
                            "evidence_payload": {
                                "loser_duration_seconds": l_dur,
                                "median_winner_seconds": median_win_sec,
                                "duration_multiplier": str(mult),
                                "loss_amount": str(l.realized_net_pnl),
                            },
                            "affected_metrics": {
                                "loser_holding_duration": l_dur,
                            },
                            "status": "DETECTED",
                        })

            # 2. Winner Cutting Detector (Rushed small win after a loss)
            for i in range(1, len(trades)):
                t_curr = trades[i]
                t_prev = trades[i - 1]
                if t_prev.realized_net_pnl < Decimal("0.0000") and t_curr.realized_net_pnl > Decimal("0.0000"):
                    w_close = t_curr.closed_at_utc or t_curr.opened_at_utc
                    w_dur = max(0, int((w_close - t_curr.opened_at_utc).total_seconds()))
                    if w_dur <= 60 and t_curr.realized_net_pnl <= Decimal("0.20") * avg_win_pnl:
                        results.append({
                            "tenant_id": context.tenant_id,
                            "broker": context.broker,
                            "account_number": context.account_number,
                            "server_name": context.server_name,
                            "reconstruction_run_id": context.reconstruction_run_id,
                            "pattern_type": "POSSIBLE_WINNER_CUTTING",
                            "detection_rule_version": PATTERN_RULE_VERSION,
                            "detection_status": "RULE_MATCHED",
                            "severity": "LOW",
                            "evidence_strength": "MODERATE",
                            "window_start_utc": t_curr.opened_at_utc,
                            "window_end_utc": w_close,
                            "supporting_trade_ids": [str(t_prev.id), str(t_curr.id)],
                            "evidence_payload": {
                                "winner_duration_seconds": w_dur,
                                "realized_profit": str(t_curr.realized_net_pnl),
                                "average_winner_profit": str(avg_win_pnl.quantize(Decimal("0.0001"))),
                                "prior_trade_loss": str(t_prev.realized_net_pnl),
                            },
                            "affected_metrics": {
                                "win_duration": w_dur,
                                "profit_captured": str(t_curr.realized_net_pnl),
                            },
                            "status": "DETECTED",
                        })
        return results

    @classmethod
    def _detect_rapid_reentry(
        cls,
        trades: list[CanonicalTrade],
        context: AnalyticsCalculationContext,
    ) -> list[dict[str, Any]]:
        """
        Detects rapid same-symbol re-entry within < 30 seconds of an exit.
        """
        results = []
        for i in range(len(trades) - 1):
            t_curr = trades[i]
            t_next = trades[i + 1]

            if t_curr.symbol == t_next.symbol:
                close_dt = t_curr.closed_at_utc or t_curr.opened_at_utc
                open_dt = t_next.opened_at_utc
                delta_sec = int((open_dt - close_dt).total_seconds())

                if 0 <= delta_sec < 30:
                    results.append({
                        "tenant_id": context.tenant_id,
                        "broker": context.broker,
                        "account_number": context.account_number,
                        "server_name": context.server_name,
                        "reconstruction_run_id": context.reconstruction_run_id,
                        "pattern_type": "POSSIBLE_RAPID_RE_ENTRY",
                        "detection_rule_version": PATTERN_RULE_VERSION,
                        "detection_status": "RULE_MATCHED",
                        "severity": "LOW",
                        "evidence_strength": "MODERATE",
                        "window_start_utc": close_dt,
                        "window_end_utc": t_next.closed_at_utc or open_dt,
                        "supporting_trade_ids": [str(t_curr.id), str(t_next.id)],
                        "evidence_payload": {
                            "symbol": t_curr.symbol,
                            "delta_seconds": delta_sec,
                            "side_first": t_curr.side,
                            "side_second": t_next.side,
                        },
                        "affected_metrics": {
                            "inter_trade_interval_sec": delta_sec,
                        },
                        "status": "DETECTED",
                    })
        return results

    @classmethod
    def _detect_session_deterioration(
        cls,
        trades: list[CanonicalTrade],
        context: AnalyticsCalculationContext,
    ) -> list[dict[str, Any]]:
        """
        Detects session deterioration where trading results decay significantly in the
        second half of an extended session (>= 4 hours, >= 6 trades).
        """
        if len(trades) < 6:
            return []

        results = []
        # Group by calendar day
        days: dict[str, list[CanonicalTrade]] = {}
        for t in trades:
            day_str = t.opened_at_utc.strftime("%Y-%m-%d")
            days.setdefault(day_str, []).append(t)

        for day_str, day_trades in days.items():
            if len(day_trades) >= 6:
                first_t = day_trades[0].opened_at_utc
                last_t = day_trades[-1].closed_at_utc or day_trades[-1].opened_at_utc
                span_hours = (last_t - first_t).total_seconds() / 3600.0

                if span_hours >= 4.0:
                    midpoint = len(day_trades) // 2
                    first_half = day_trades[:midpoint]
                    second_half = day_trades[midpoint:]

                    pnl_1 = sum(t.realized_net_pnl for t in first_half)
                    pnl_2 = sum(t.realized_net_pnl for t in second_half)
                    wins_1 = sum(1 for t in first_half if t.realized_net_pnl > Decimal("0.0000"))
                    wins_2 = sum(1 for t in second_half if t.realized_net_pnl > Decimal("0.0000"))

                    wr_1 = Decimal(wins_1) / Decimal(len(first_half))
                    wr_2 = Decimal(wins_2) / Decimal(len(second_half))

                    if pnl_1 > Decimal("0.0000") and pnl_2 < Decimal("0.0000") and (wr_1 - wr_2) >= Decimal("0.2500"):
                        results.append({
                            "tenant_id": context.tenant_id,
                            "broker": context.broker,
                            "account_number": context.account_number,
                            "server_name": context.server_name,
                            "reconstruction_run_id": context.reconstruction_run_id,
                            "pattern_type": "POSSIBLE_SESSION_DETERIORATION",
                            "detection_rule_version": PATTERN_RULE_VERSION,
                            "detection_status": "RULE_MATCHED",
                            "severity": "MEDIUM",
                            "evidence_strength": "STRONG",
                            "window_start_utc": first_t,
                            "window_end_utc": last_t,
                            "supporting_trade_ids": [str(t.id) for t in day_trades],
                            "evidence_payload": {
                                "session_duration_hours": f"{span_hours:.1f}",
                                "first_half_pnl": str(pnl_1.quantize(Decimal("0.0001"))),
                                "second_half_pnl": str(pnl_2.quantize(Decimal("0.0001"))),
                                "first_half_win_rate": str(wr_1.quantize(Decimal("0.0001"))),
                                "second_half_win_rate": str(wr_2.quantize(Decimal("0.0001"))),
                            },
                            "affected_metrics": {
                                "late_session_pnl_decay": str((pnl_1 - pnl_2).quantize(Decimal("0.0001"))),
                            },
                            "status": "DETECTED",
                        })
        return results

    @classmethod
    def _detect_drawdown_acceleration(
        cls,
        trades: list[CanonicalTrade],
        context: AnalyticsCalculationContext,
        initial_balance: Decimal,
    ) -> list[dict[str, Any]]:
        """
        Detects sudden drawdown acceleration where cumulative loss exceeds >= 10%
        of equity in <= 2 hours.
        """
        if len(trades) < 3 or initial_balance <= Decimal("0.0000"):
            return []

        results = []
        last_flagged_end: Optional[datetime] = None
        n = len(trades)
        right = 0
        w_delta = timedelta(hours=2)

        for left in range(n):
            t_left = trades[left]
            w_start = t_left.opened_at_utc
            if last_flagged_end and w_start < last_flagged_end:
                continue
            w_end = w_start + w_delta

            if right < left:
                right = left
            while right < n and (trades[right].closed_at_utc or trades[right].opened_at_utc) <= w_end:
                right += 1

            window_trades = trades[left:right]
            if len(window_trades) >= 2:
                net_loss = sum(t.realized_net_pnl for t in window_trades if t.realized_net_pnl < Decimal("0.0000"))
                if abs(net_loss) >= Decimal("0.10") * initial_balance:
                    trade_ids = [str(t.id) for t in window_trades]
                    last_flagged_end = w_end
                    results.append({
                        "tenant_id": context.tenant_id,
                        "broker": context.broker,
                        "account_number": context.account_number,
                        "server_name": context.server_name,
                        "reconstruction_run_id": context.reconstruction_run_id,
                        "pattern_type": "POSSIBLE_DRAWDOWN_ACCELERATION",
                        "detection_rule_version": PATTERN_RULE_VERSION,
                        "detection_status": "RULE_MATCHED",
                        "severity": "CRITICAL",
                        "evidence_strength": "STRONG",
                        "window_start_utc": w_start,
                        "window_end_utc": w_end,
                        "supporting_trade_ids": trade_ids,
                        "evidence_payload": {
                            "rapid_loss_amount": str(net_loss),
                            "loss_pct_of_capital": str((abs(net_loss) / initial_balance).quantize(Decimal("0.0001"))),
                            "time_window_hours": "2.0",
                        },
                        "affected_metrics": {
                            "max_drawdown_amount": str(abs(net_loss)),
                        },
                        "status": "DETECTED",
                    })
        return results
