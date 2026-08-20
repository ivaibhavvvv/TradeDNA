"""TradeDNA Phase 7 - Master Analytics Orchestration Service.
Orchestrates the execution of all Phase 7 analytics engines across canonical trades,
persists immutable snapshot and feature records, and delivers auditable trade intelligence.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, Sequence
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.analytics import (
    AnalyticsFeatureStore,
    AnalyticsSnapshot,
    BaselineComparison,
    BehavioralPattern,
    TradingDNAProfile,
)
from src.models.canonical_ledger import CanonicalTrade
from src.services.analytics_baseline_engine import AnalyticsBaselineEngine
from src.services.analytics_behavior_engine import AnalyticsBehaviorEngine
from src.services.analytics_context import (
    AnalyticsCalculationContext,
    AnalyticsContextResolver,
)
from src.services.analytics_dna_engine import AnalyticsDNAEngine
from src.services.analytics_pattern_engine import AnalyticsPatternEngine
from src.services.analytics_performance_engine import AnalyticsPerformanceEngine
from src.services.double_entry_ledger_engine import DoubleEntryLedgerEngine


def serialize_for_json(obj: Any) -> Any:
    """Recursively converts Decimals, UUIDs, and datetimes into JSON-safe types."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [serialize_for_json(item) for item in obj]
    return obj


class AnalyticsService:
    """
    Main orchestration service for Phase 7 Trade Intelligence & Behavioral Analytics.
    """

    @classmethod
    async def compute_and_persist_analytics(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
        server_name: Optional[str] = None,
        period_type: str = "ALL_TIME",
        start_time_utc: Optional[datetime] = None,
        end_time_utc: Optional[datetime] = None,
        target_reconstruction_run_id: Optional[uuid.UUID] = None,
        target_reconciliation_run_id: Optional[uuid.UUID] = None,
    ) -> dict[str, Any]:
        """
        Executes full analytics pipeline and persists results into database.
        """
        # 1. Resolve Calculation Context & Integrity Gate
        context = await AnalyticsContextResolver.resolve_context(
            session=session,
            tenant_id=tenant_id,
            account_number=account_number,
            server_name=server_name,
            target_reconstruction_run_id=target_reconstruction_run_id,
            target_reconciliation_run_id=target_reconciliation_run_id,
            period_start=start_time_utc,
            period_end=end_time_utc,
        )

        # 2. Fetch Canonical Trades for target reconstruction run
        stmt_trades = (
            select(CanonicalTrade)
            .where(
                CanonicalTrade.tenant_id == tenant_id,
                CanonicalTrade.account_number == account_number,
                CanonicalTrade.reconstruction_run_id == context.reconstruction_run_id,
            )
            .order_by(CanonicalTrade.opened_at_utc.asc())
        )
        if start_time_utc:
            stmt_trades = stmt_trades.where(CanonicalTrade.opened_at_utc >= start_time_utc)
        if end_time_utc:
            stmt_trades = stmt_trades.where(CanonicalTrade.opened_at_utc <= end_time_utc)

        res_trades = await session.execute(stmt_trades)
        trades = res_trades.scalars().all()

        # Resolve initial starting balance from ledger
        initial_balance = Decimal("0.0000")
        running_bal = await DoubleEntryLedgerEngine.get_running_balance_projection(
            session=session,
            reconstruction_run_id=context.reconstruction_run_id,
            account_number=account_number,
        )
        if running_bal > Decimal("0.0000"):
            initial_balance = running_bal

        # 3. Calculate Performance & Drawdown Metrics
        perf_data = AnalyticsPerformanceEngine.calculate_trade_metrics(
            trades=trades,
            context=context,
            initial_balance=initial_balance,
        )

        # Determine snapshot time window
        now_utc = datetime.now(timezone.utc)
        s_start = start_time_utc or (trades[0].opened_at_utc if trades else now_utc)
        s_end = end_time_utc or now_utc

        # Persist AnalyticsSnapshot
        snapshot = AnalyticsSnapshot(
            tenant_id=context.tenant_id,
            broker=context.broker,
            account_number=context.account_number,
            server_name=context.server_name,
            reconstruction_run_id=context.reconstruction_run_id,
            reconciliation_run_id=context.reconciliation_run_id,
            period_type=period_type,
            start_time_utc=s_start,
            end_time_utc=s_end,
            total_trades=perf_data["total_trades"],
            winning_trades=perf_data["winning_trades"],
            losing_trades=perf_data["losing_trades"],
            breakeven_trades=perf_data["breakeven_trades"],
            win_rate=perf_data["win_rate"],
            loss_rate=perf_data["loss_rate"],
            gross_profit=perf_data["gross_profit"],
            gross_loss=perf_data["gross_loss"],
            net_pnl=perf_data["net_pnl"],
            profit_factor=perf_data["profit_factor"],
            expectancy=perf_data["expectancy"],
            payoff_ratio=perf_data["payoff_ratio"],
            avg_trade=perf_data["avg_trade"],
            median_trade=perf_data["median_trade"],
            avg_winner=perf_data["avg_winner"],
            avg_loser=perf_data["avg_loser"],
            largest_winner=perf_data["largest_winner"],
            largest_loser=perf_data["largest_loser"],
            max_drawdown_amount=perf_data["max_drawdown_amount"],
            max_drawdown_pct=perf_data["max_drawdown_pct"],
            recovery_factor=perf_data["recovery_factor"],
            drawdown_duration_sec=perf_data["drawdown_duration_sec"],
            recovery_duration_sec=perf_data["recovery_duration_sec"],
            avg_holding_sec=perf_data["avg_holding_sec"],
            median_holding_sec=perf_data["median_holding_sec"],
            avg_winner_holding_sec=perf_data["avg_winner_holding_sec"],
            avg_loser_holding_sec=perf_data["avg_loser_holding_sec"],
            duration_ratio=perf_data["duration_ratio"],
            total_volume_lots=perf_data["total_volume_lots"],
            avg_lot_size=perf_data["avg_lot_size"],
            max_lot_size=perf_data["max_lot_size"],
            max_consecutive_wins=perf_data["max_consecutive_wins"],
            max_consecutive_losses=perf_data["max_consecutive_losses"],
            hhi_symbol_concentration=perf_data["hhi_symbol_concentration"],
            top_symbol_volume_pct=perf_data["top_symbol_volume_pct"],
            currency=context.reporting_currency,
            is_compromised=context.is_compromised,
            data_integrity_score=context.data_integrity_score,
            integrity_grade=context.integrity_grade,
            calculation_version=context.calculation_engine_version,
            metrics_json=serialize_for_json(perf_data),
        )
        session.add(snapshot)

        # 4. Compute & Persist Dimensional Feature Store Cubes
        feature_cubes = AnalyticsBehaviorEngine.compute_feature_cubes(trades, context)
        for cube_data in feature_cubes:
            feat = AnalyticsFeatureStore(
                tenant_id=cube_data["tenant_id"],
                broker=cube_data["broker"],
                account_number=cube_data["account_number"],
                server_name=cube_data["server_name"],
                reconstruction_run_id=cube_data["reconstruction_run_id"],
                dimension_type=cube_data["dimension_type"],
                dimension_key=cube_data["dimension_key"],
                trade_count=cube_data["trade_count"],
                win_count=cube_data["win_count"],
                loss_count=cube_data["loss_count"],
                volume_lots=cube_data["volume_lots"],
                gross_profit=cube_data["gross_profit"],
                gross_loss=cube_data["gross_loss"],
                net_pnl=cube_data["net_pnl"],
                profit_factor=cube_data["profit_factor"],
                win_rate=cube_data["win_rate"],
                expectancy=cube_data["expectancy"],
                avg_holding_sec=cube_data["avg_holding_sec"],
                features_json=serialize_for_json(cube_data["features_json"]),
                calculation_version=cube_data["calculation_version"],
            )
            session.add(feat)

        # 5. Detect & Persist Behavioral Patterns
        detected_patterns = AnalyticsPatternEngine.detect_all_patterns(
            trades=trades,
            context=context,
            initial_balance=initial_balance or Decimal("10000.0000"),
        )
        for pat_data in detected_patterns:
            pat = BehavioralPattern(
                tenant_id=pat_data["tenant_id"],
                broker=pat_data["broker"],
                account_number=pat_data["account_number"],
                server_name=pat_data["server_name"],
                reconstruction_run_id=pat_data["reconstruction_run_id"],
                pattern_type=pat_data["pattern_type"],
                detection_rule_version=pat_data["detection_rule_version"],
                detection_status=pat_data["detection_status"],
                severity=pat_data["severity"],
                evidence_strength=pat_data["evidence_strength"],
                window_start_utc=pat_data["window_start_utc"],
                window_end_utc=pat_data["window_end_utc"],
                supporting_trade_ids=serialize_for_json(pat_data["supporting_trade_ids"]),
                evidence_payload=serialize_for_json(pat_data["evidence_payload"]),
                affected_metrics=serialize_for_json(pat_data["affected_metrics"]),
                status=pat_data["status"],
            )
            session.add(pat)

        # 6. Compute & Persist Baseline Comparisons
        baseline_comps = AnalyticsBaselineEngine.compute_all_baselines(trades, context)
        for base_data in baseline_comps:
            b_comp = BaselineComparison(
                tenant_id=base_data["tenant_id"],
                broker=base_data["broker"],
                account_number=base_data["account_number"],
                server_name=base_data["server_name"],
                reconstruction_run_id=base_data["reconstruction_run_id"],
                comparison_cohort=base_data["comparison_cohort"],
                current_start_utc=base_data["current_start_utc"],
                current_end_utc=base_data["current_end_utc"],
                baseline_start_utc=base_data["baseline_start_utc"],
                baseline_end_utc=base_data["baseline_end_utc"],
                metric_comparisons=serialize_for_json(base_data["metric_comparisons"]),
                detected_drifts=serialize_for_json(base_data["detected_drifts"]),
                overall_trajectory=base_data["overall_trajectory"],
                calculation_version=base_data["calculation_version"],
            )
            session.add(b_comp)

        # 7. Synthesize & Persist Trading DNA Profile
        dna_data = AnalyticsDNAEngine.synthesize_dna_profile(trades, detected_patterns, context, metrics=perf_data)
        dna_profile = TradingDNAProfile(
            tenant_id=dna_data["tenant_id"],
            broker=dna_data["broker"],
            account_number=dna_data["account_number"],
            server_name=dna_data["server_name"],
            reconstruction_run_id=dna_data["reconstruction_run_id"],
            primary_trading_style=dna_data["primary_trading_style"],
            risk_appetite_grade=dna_data["risk_appetite_grade"],
            consistency_score=dna_data["consistency_score"],
            discipline_score=dna_data["discipline_score"],
            execution_quality_score=dna_data["execution_quality_score"],
            favored_instruments=serialize_for_json(dna_data["favored_instruments"]),
            favored_sessions=serialize_for_json(dna_data["favored_sessions"]),
            radar_dimensions=serialize_for_json(dna_data["radar_dimensions"]),
            top_strengths=serialize_for_json(dna_data["top_strengths"]),
            top_weaknesses=serialize_for_json(dna_data["top_weaknesses"]),
            behavioral_tendencies=serialize_for_json(dna_data["behavioral_tendencies"]),
            calculation_version=dna_data["calculation_version"],
            synthesized_at=dna_data["synthesized_at"],
        )
        session.add(dna_profile)

        await session.flush()

        return {
            "snapshot_id": snapshot.id,
            "context": context,
            "performance": perf_data,
            "feature_cubes_count": len(feature_cubes),
            "patterns_count": len(detected_patterns),
            "detected_patterns": detected_patterns,
            "baseline_comparisons": baseline_comps,
            "trading_dna": dna_data,
            "is_compromised": context.is_compromised,
            "data_trust_status": context.data_trust_status,
            "quality_warnings": list(context.quality_warnings),
        }
