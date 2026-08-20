from datetime import datetime, timezone
from typing import Any, Optional
import uuid
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, UUIDPrimaryKeyMixin


class AccountSyncState(Base, UUIDPrimaryKeyMixin):
    """Authoritative logical financial synchronization state scoped by 4-tuple:
    (tenant_id, broker, account_number, server_name)."""

    __tablename__ = "account_sync_states"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    broker: Mapped[str] = mapped_column(String(32), nullable=False, default="EXNESS")
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    trade_mode: Mapped[str] = mapped_column(String(10), nullable=False)  # REAL, DEMO, CONTEST
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="INITIALIZING")
    # INITIALIZING, SYNCING, CURRENT, STALE, DEGRADED, GAP_DETECTED, RECONCILING, ERROR
    current_cursor_time_msc: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    current_cursor_deal_ticket: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_synced_device_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_successful_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_batch_idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reconciled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_anomalies_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_reconstruction_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconstruction_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    gap_events: Mapped[list["SyncGapEvent"]] = relationship(
        "SyncGapEvent", back_populates="account_sync", cascade="none"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "broker", "account_number", "server_name", name="uq_account_sync_4tuple"),
        Index("idx_account_sync_lookup", "tenant_id", "broker", "account_number", "server_name"),
    )


class SyncGapEvent(Base, UUIDPrimaryKeyMixin):
    """Synchronization anomalies and gap records."""

    __tablename__ = "sync_gap_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_sync_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("account_sync_states.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    gap_classification: Mapped[str] = mapped_column(String(32), nullable=False)
    # CONFIRMED_GAP, POSSIBLE_GAP, NO_GAP, INSUFFICIENT_INFORMATION
    anomaly_category: Mapped[str] = mapped_column(String(64), nullable=False)
    # CURSOR_REGRESSION, BOUNDED_WINDOW_OMISSION, CONFLICTING_PAYLOAD, TICKET_SEQUENCE_JUMP, EXTENDED_SILENCE, SNAPSHOT_EQUITY_DIVERGENCE
    evidence_details: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    account_sync: Mapped["AccountSyncState"] = relationship("AccountSyncState", back_populates="gap_events")
