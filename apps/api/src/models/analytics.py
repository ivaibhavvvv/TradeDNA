"""TradeDNA Phase 7 - Analytics, Behavioral Intelligence & Trading DNA Models.
Defines immutable/versioned analytical snapshots, dimensional feature stores,
behavioral pattern records, Trading DNA profiles, and historical baseline comparisons.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
import uuid
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Cross-dialect JSON column helper
JSONType = JSON().with_variant(JSONB(), "postgresql")


class AnalyticsSnapshot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Authoritative account-level performance and risk snapshot for a specific
    time period (ALL_TIME, LAST_7D, LAST_30D, LAST_90D, CALENDAR_MONTH, CUSTOM).
    Strictly tied to a specific ReconstructionRun and ReconciliationRun.
    """
    __tablename__ = "analytics_snapshots"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    broker: Mapped[str] = mapped_column(String(50), default="EXNESS", nullable=False)
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(100), nullable=False)

    reconstruction_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconstruction_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reconciliation_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconciliation_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    period_type: Mapped[str] = mapped_column(String(32), nullable=False)
    start_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # --- Performance Metrics ---
    total_trades: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    winning_trades: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    losing_trades: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    breakeven_trades: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    win_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.0000"), nullable=False)
    loss_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.0000"), nullable=False)

    gross_profit: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    gross_loss: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    net_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    profit_factor: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"), nullable=False)
    expectancy: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    payoff_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"), nullable=False)

    avg_trade: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    median_trade: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    avg_winner: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    avg_loser: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    largest_winner: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    largest_loser: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)

    # --- Drawdown Metrics ---
    max_drawdown_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    max_drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.0000"), nullable=False)
    recovery_factor: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"), nullable=False)
    drawdown_duration_sec: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    recovery_duration_sec: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # --- Behavior & Duration Metrics ---
    avg_holding_sec: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    median_holding_sec: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    avg_winner_holding_sec: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    avg_loser_holding_sec: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    duration_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"), nullable=False)

    total_volume_lots: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    avg_lot_size: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    max_lot_size: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)

    max_consecutive_wins: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    max_consecutive_losses: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # --- Risk & Concentration Metrics ---
    hhi_symbol_concentration: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0.00"), nullable=False)
    top_symbol_volume_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.0000"), nullable=False)

    # --- Lineage & Quality Metadata ---
    currency: Mapped[str] = mapped_column(String(16), default="USD", nullable=False)
    is_compromised: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    data_integrity_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("100.00"), nullable=False)
    integrity_grade: Mapped[str] = mapped_column(String(8), default="AAA", nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(24), default="7.0.0", nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_analytics_snap_acc_period", "tenant_id", "account_number", "period_type", "end_time_utc"),
        Index("ix_analytics_snap_run", "reconstruction_run_id"),
    )


class AnalyticsFeatureStore(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Pre-aggregated dimensional analytical cube storing performance metrics
    sliced by SYMBOL, SESSION, DAY_OF_WEEK, HOUR_OF_DAY, DIRECTION, etc.
    """
    __tablename__ = "analytics_feature_store"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    broker: Mapped[str] = mapped_column(String(50), default="EXNESS", nullable=False)
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(100), nullable=False)

    reconstruction_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconstruction_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    dimension_type: Mapped[str] = mapped_column(String(32), nullable=False)  # SYMBOL, SESSION, DAY_OF_WEEK, HOUR_OF_DAY, DIRECTION
    dimension_key: Mapped[str] = mapped_column(String(64), nullable=False)

    trade_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    win_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    loss_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    volume_lots: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    gross_profit: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    gross_loss: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    net_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    profit_factor: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"), nullable=False)
    win_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.0000"), nullable=False)
    expectancy: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    avg_holding_sec: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    features_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(24), default="7.0.0", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "account_number", "reconstruction_run_id", "dimension_type", "dimension_key", name="uq_feature_dim_key"),
        Index("ix_feature_store_acc_dim", "tenant_id", "account_number", "dimension_type"),
    )


class BehavioralPattern(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Deterministic rule-based behavioral anomaly detections (e.g. Revenge Trading,
    Overtrading Spike, Loss Escalation / Martingale, Loser Holding, Winner Cutting).
    """
    __tablename__ = "behavioral_patterns"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    broker: Mapped[str] = mapped_column(String(50), default="EXNESS", nullable=False)
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(100), nullable=False)

    reconstruction_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconstruction_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    pattern_type: Mapped[str] = mapped_column(String(48), nullable=False)  # REVENGE_TRADING, OVERTRADING_SPIKE, LOSS_ESCALATION, etc.
    detection_rule_version: Mapped[str] = mapped_column(String(24), default="1.0.0", nullable=False)
    detection_status: Mapped[str] = mapped_column(String(24), default="RULE_MATCHED", nullable=False)  # RULE_MATCHED, INSUFFICIENT_SAMPLE
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    evidence_strength: Mapped[str] = mapped_column(String(24), default="STRONG", nullable=False)  # STRONG, MODERATE, WEAK

    window_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    supporting_trade_ids: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    evidence_payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    affected_metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)

    status: Mapped[str] = mapped_column(String(24), default="DETECTED", nullable=False)  # DETECTED, ACKNOWLEDGED, DISMISSED

    __table_args__ = (
        Index("ix_behavioral_pat_acc_type", "tenant_id", "account_number", "pattern_type", "severity"),
        Index("ix_behavioral_pat_time", "tenant_id", "account_number", "window_start_utc"),
    )


class TradingDNAProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Synthesized multi-dimensional profile characterizing trading style,
    consistency, risk appetite, execution profile, strengths, and weaknesses.
    """
    __tablename__ = "trading_dna_profiles"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    broker: Mapped[str] = mapped_column(String(50), default="EXNESS", nullable=False)
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(100), nullable=False)

    reconstruction_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconstruction_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    primary_trading_style: Mapped[str] = mapped_column(String(32), nullable=False)  # SCALPER, DAY_TRADER, SWING_TRADER, POSITION_TRADER
    risk_appetite_grade: Mapped[str] = mapped_column(String(24), nullable=False)   # CONSERVATIVE, MODERATE, AGGRESSIVE, TOXIC_RISK
    consistency_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)  # 0.00 to 100.00
    discipline_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)   # 0.00 to 100.00
    execution_quality_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("100.00"), nullable=False)

    favored_instruments: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    favored_sessions: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    radar_dimensions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)

    top_strengths: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    top_weaknesses: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    behavioral_tendencies: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)

    calculation_version: Mapped[str] = mapped_column(String(24), default="7.0.0", nullable=False)
    synthesized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_dna_profiles_acc", "tenant_id", "account_number", "synthesized_at"),
    )


class BaselineComparison(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Statistical and behavioral drift comparison between current period
    and a historical baseline (e.g. 7D vs 30D, 30D vs 90D, Month vs Historical).
    """
    __tablename__ = "baseline_comparisons"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    broker: Mapped[str] = mapped_column(String(50), default="EXNESS", nullable=False)
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(100), nullable=False)

    reconstruction_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconstruction_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    comparison_cohort: Mapped[str] = mapped_column(String(48), nullable=False)  # CURRENT_7D_VS_PREV_30D, CURRENT_30D_VS_PREV_90D, etc.
    current_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    baseline_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    baseline_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    metric_comparisons: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    detected_drifts: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    overall_trajectory: Mapped[str] = mapped_column(String(24), default="STABLE", nullable=False)  # IMPROVING, STABLE, DEGRADING, HIGH_RISK_SHIFT

    calculation_version: Mapped[str] = mapped_column(String(24), default="7.0.0", nullable=False)

    __table_args__ = (
        Index("ix_baseline_comp_acc", "tenant_id", "account_number", "comparison_cohort"),
    )
