from datetime import datetime, timezone
from decimal import Decimal
import uuid
from typing import Any, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    Numeric,
    String,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.exceptions import TradeDNAException
from src.models.base import Base, UUIDPrimaryKeyMixin


class ImmutabilityViolationException(TradeDNAException):
    def __init__(self, table_name: str):
        super().__init__(
            status_code=500,
            code="DATABASE_IMMUTABILITY_VIOLATION",
            message=f"Layer 1 raw table '{table_name}' is append-only. UPDATE and DELETE operations are strictly forbidden.",
        )


class RawIngressPayload(Base, UUIDPrimaryKeyMixin):
    """Authoritative Layer 1 record of the exact HTTP request body received from connectors."""

    __tablename__ = "raw_ingress_payloads"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_type: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0.0")
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_payload_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    raw_payload_json: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    received_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    observations: Mapped[list["RawEventObservation"]] = relationship(
        "RawEventObservation", back_populates="ingress_payload", cascade="none"
    )
    account_snapshots: Mapped[list["RawAccountSnapshot"]] = relationship(
        "RawAccountSnapshot", back_populates="ingress_payload", cascade="none"
    )
    position_snapshots: Mapped[list["RawPositionSnapshot"]] = relationship(
        "RawPositionSnapshot", back_populates="ingress_payload", cascade="none"
    )


class RawEventObservation(Base, UUIDPrimaryKeyMixin):
    """Individual observed MT5 event (deal, order) pointing to parent raw ingress bytes."""

    __tablename__ = "raw_event_observations"

    observation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        unique=True,
        nullable=False,
        index=True,
    )
    ingress_payload_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("raw_ingress_payloads.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # HISTORICAL_SYNC, INCREMENTAL_SYNC, ON_TRADE_TRANSACTION, BACKFILL
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)   # DEAL_EVENT, ORDER_EVENT
    external_ticket: Mapped[int] = mapped_column(BigInteger, nullable=False)
    external_event_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    item_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_item_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    observation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ORIGINAL")  # ORIGINAL, DUPLICATE, CONFLICTING
    source_time_msc: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    ingress_payload: Mapped["RawIngressPayload"] = relationship("RawIngressPayload", back_populates="observations")

    __table_args__ = (
        Index("idx_raw_obs_ext_id", "tenant_id", "account_number", "event_type", "external_ticket"),
        Index("idx_raw_obs_replay_deal", "tenant_id", "account_number", "source_time_msc", "external_ticket", "observation_id"),
        Index("idx_raw_obs_replay_order", "tenant_id", "account_number", "source_time_msc", "external_ticket", "observation_id"),
    )


class RawAccountSnapshot(Base, UUIDPrimaryKeyMixin):
    """Layer 1 snapshot of account financial state."""

    __tablename__ = "raw_account_snapshots"

    ingress_payload_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("raw_ingress_payloads.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    margin: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    margin_free: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    margin_level: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    trade_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    is_hedging: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    raw_payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    snapshot_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    ingress_payload: Mapped["RawIngressPayload"] = relationship("RawIngressPayload", back_populates="account_snapshots")

    __table_args__ = (
        Index("idx_raw_snap_replay", "tenant_id", "account_number", "snapshot_time_utc", "received_at_utc", "id"),
    )


class RawPositionSnapshot(Base, UUIDPrimaryKeyMixin):
    """Layer 1 snapshot of open positions."""

    __tablename__ = "raw_position_snapshots"

    ingress_payload_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("raw_ingress_payloads.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False)
    position_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    snapshot_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    ingress_payload: Mapped["RawIngressPayload"] = relationship("RawIngressPayload", back_populates="position_snapshots")

    __table_args__ = (
        Index("idx_raw_pos_replay", "tenant_id", "account_number", "snapshot_time_utc", "received_at_utc", "id"),
    )


# =====================================================================
# Database-Level Immutability Hooks (Application Boundary Protection)
# =====================================================================
def _block_raw_mutation(mapper, connection, target):
    raise ImmutabilityViolationException(target.__tablename__)


for model_cls in [RawIngressPayload, RawEventObservation, RawAccountSnapshot, RawPositionSnapshot]:
    event.listen(model_cls, "before_update", _block_raw_mutation)
    event.listen(model_cls, "before_delete", _block_raw_mutation)
