"""TradeDNA Phase 6 - Financial Reconciliation and Data Integrity Models
Defines immutable reconciliation runs, discrepancy items with broker vs canonical truth,
account/position comparison summaries, remediation proposals, and data integrity score history.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
import uuid
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, UUIDPrimaryKeyMixin


class ReconciliationRun(Base, UUIDPrimaryKeyMixin):
    """Immutable audit record representing a discrete reconciliation execution."""

    __tablename__ = "reconciliation_runs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False)
    reconstruction_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconstruction_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("raw_account_snapshots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reconciliation_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="POINT_IN_TIME_SNAPSHOT",
    )  # POINT_IN_TIME_SNAPSHOT, HISTORICAL_WINDOW, CONTINUOUS_STREAMING, EOD_AUDIT
    as_of_time_msc: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    as_of_timestamp_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    window_start_msc: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    window_end_msc: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="PENDING",
    )  # PENDING, IN_PROGRESS, COMPLETED, FAILED

    discrepancy_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    low_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    info_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    data_integrity_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("100.00"),
    )
    integrity_grade: Mapped[str] = mapped_column(String(8), nullable=False, default="AAA")
    is_clean: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Immutable Configuration Versions for Exact Replay Reproducibility
    reconciliation_engine_version: Mapped[str] = mapped_column(String(24), nullable=False, default="6.0.0")
    tolerance_profile_version: Mapped[str] = mapped_column(String(24), nullable=False, default="1.0.0")
    severity_policy_version: Mapped[str] = mapped_column(String(24), nullable=False, default="1.0.0")
    instrument_spec_version: Mapped[str] = mapped_column(String(24), nullable=False, default="1.0.0")
    fx_source_version: Mapped[str] = mapped_column(String(24), nullable=False, default="1.0.0")

    execution_time_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    discrepancies: Mapped[list["ReconciliationDiscrepancy"]] = relationship(
        "ReconciliationDiscrepancy",
        back_populates="reconciliation_run",
        cascade="all, delete-orphan",
    )
    account_summary: Mapped[Optional["ReconciliationAccountSummary"]] = relationship(
        "ReconciliationAccountSummary",
        back_populates="reconciliation_run",
        uselist=False,
        cascade="all, delete-orphan",
    )
    position_summaries: Mapped[list["ReconciliationPositionSummary"]] = relationship(
        "ReconciliationPositionSummary",
        back_populates="reconciliation_run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_recon_runs_account_time", "tenant_id", "account_number", "as_of_time_msc"),
        Index("idx_recon_runs_status_clean", "status", "is_clean"),
    )


class ReconciliationDiscrepancy(Base, UUIDPrimaryKeyMixin):
    """Detailed financial variance item comparing broker truth against canonical truth."""

    __tablename__ = "reconciliation_discrepancies"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconciliation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False)

    discrepancy_scope: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
    )  # ACCOUNT_LEVEL, POSITION_LEVEL, EVENT_LEVEL, LEDGER_LEVEL
    discrepancy_category: Mapped[str] = mapped_column(
        String(48),
        nullable=False,
        index=True,
    )  # BALANCE_MISMATCH, EQUITY_MISMATCH, etc.
    severity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
    )  # CRITICAL, HIGH, MEDIUM, LOW, INFO

    entity_type: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
    )  # ACCOUNT, POSITION, TRADE, EXECUTION, DEAL, POSTING, BALANCE_EVENT
    entity_identifier: Mapped[str] = mapped_column(String(128), nullable=False)

    # Independent Authoritative Value Comparisons
    broker_value: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_value: Mapped[str] = mapped_column(String(128), nullable=False)
    delta_value: Mapped[str] = mapped_column(String(128), nullable=False)
    broker_source: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_source: Mapped[str] = mapped_column(String(128), nullable=False)

    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="USD")
    tolerance_applied: Mapped[str] = mapped_column(String(32), nullable=False)

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="OPEN",
    )  # OPEN, ACKNOWLEDGED, REMEDIATED, SUPERSEDED, EXPLAINED_BROKER_ANOMALY
    root_cause_category: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    remediation_proposal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("remediation_proposals.id", ondelete="SET NULL"),
        nullable=True,
    )
    details_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )

    acknowledged_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledgement_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    reconciliation_run: Mapped["ReconciliationRun"] = relationship(
        "ReconciliationRun",
        back_populates="discrepancies",
    )

    __table_args__ = (
        Index("idx_recon_disc_run_severity", "reconciliation_run_id", "severity"),
        Index("idx_recon_disc_account_status", "tenant_id", "account_number", "status"),
    )


class ReconciliationAccountSummary(Base, UUIDPrimaryKeyMixin):
    """Account-level financial metrics matrix comparing snapshot to canonical state."""

    __tablename__ = "reconciliation_account_summaries"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconciliation_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)

    # MT5 Broker Snapshot
    mt5_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    mt5_equity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    mt5_margin: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    mt5_free_margin: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    mt5_floating_pl: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    # Canonical Ledger Truth
    canonical_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    canonical_equity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    canonical_margin: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    canonical_free_margin: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    canonical_floating_pl: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    # Deltas (Broker - Canonical)
    balance_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    equity_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    margin_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    free_margin_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    floating_pl_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    reconciliation_run: Mapped["ReconciliationRun"] = relationship(
        "ReconciliationRun",
        back_populates="account_summary",
    )


class ReconciliationPositionSummary(Base, UUIDPrimaryKeyMixin):
    """Position-level matrix comparing MT5 open positions to canonical open trades."""

    __tablename__ = "reconciliation_position_summaries"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconciliation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    position_ticket: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)

    # MT5 Broker Position Snapshot
    mt5_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    mt5_price_open: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    mt5_price_current: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    mt5_profit: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    mt5_swap: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    # Canonical Trade State
    canonical_open_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    canonical_vwap_entry: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    canonical_floating_pl: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    canonical_swap: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    # Deltas
    volume_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    price_delta: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    profit_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    # Market Timing & Spec Lineage Context
    market_price_used: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    market_price_timestamp_msc: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fx_rate_used: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("1.000000"))
    fx_rate_source: Mapped[str] = mapped_column(String(64), nullable=False, default="DEFAULT")
    instrument_spec_version: Mapped[str] = mapped_column(String(24), nullable=False, default="1.0.0")

    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="MATCHED",
    )  # MATCHED, MISMATCHED, MISSING_CANONICAL, GHOST_CANONICAL

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    reconciliation_run: Mapped["ReconciliationRun"] = relationship(
        "ReconciliationRun",
        back_populates="position_summaries",
    )


class RemediationProposal(Base, UUIDPrimaryKeyMixin):
    """Controlled remediation state machine proposal for non-destructive healing."""

    __tablename__ = "remediation_proposals"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False)

    discrepancy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    proposal_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )  # BACKFILL_RAW_INGRESS, TRIGGER_RECONSTRUCTION_REBUILD, POST_MANUAL_ADJUSTMENT, EXPLAIN_BROKER_ANOMALY
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="DETECTED",
        index=True,
    )  # DETECTED, CLASSIFIED, REMEDIATION_PROPOSED, REMEDIATION_APPROVED, REMEDIATION_EXECUTING, VALIDATING, RESOLVED, FAILED, REJECTED

    proposed_action: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )
    execution_result: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )

    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    new_reconstruction_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconstruction_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    new_reconciliation_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconciliation_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class DataIntegrityScoreHistory(Base, UUIDPrimaryKeyMixin):
    """Historical tracking of account data integrity scores over time."""

    __tablename__ = "data_integrity_score_history"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False)
    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconciliation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    grade: Mapped[str] = mapped_column(String(8), nullable=False)
    active_discrepancies: Mapped[int] = mapped_column(Integer, nullable=False)
    critical_discrepancies: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_score_history_lookup", "tenant_id", "account_number", "recorded_at"),
    )
