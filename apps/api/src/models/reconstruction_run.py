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
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, UUIDPrimaryKeyMixin


class ReconstructionRun(Base, UUIDPrimaryKeyMixin):
    """Represents an isolated, deterministic reconstruction run / version set
    for an account's canonical financial ledger and trade history."""

    __tablename__ = "reconstruction_runs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    run_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="RUNNING",
    )  # RUNNING, ACTIVE, SUPERSEDED, FAILED, ARCHIVED
    reason: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="INITIAL_INGESTION",
    )  # INITIAL_INGESTION, HISTORICAL_BACKFILL, CORRECTION_ADJUSTMENT, SCHEMA_MIGRATION, REPLAY_AUDIT
    error_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "account_number", "run_number", name="uq_recon_run_account_num"),
        Index("idx_recon_runs_lookup", "tenant_id", "account_number", "status"),
    )
