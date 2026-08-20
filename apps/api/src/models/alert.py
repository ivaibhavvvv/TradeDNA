"""
TradeDNA Operational Alert Model
Persistent operational and financial-integrity alerts with deterministic deduplication,
strict tenant isolation, and full auditability.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.tenant import Tenant
    from src.models.user import User


class OperationalAlert(Base, UUIDPrimaryKeyMixin):
    """Operational alert record tracking system health, sync failures, and financial integrity events."""

    __tablename__ = "operational_alerts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")  # INFO, LOW, MEDIUM, HIGH, CRITICAL
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")  # OPEN, ACKNOWLEDGED, RESOLVED, SUPPRESSED
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="SYSTEM")  # RECONCILIATION, INGRESS, SYNC, SECURITY, SYSTEM
    message: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    acknowledged_by_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[acknowledged_by])
    resolved_by_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[resolved_by])

    __table_args__ = (
        Index("idx_alerts_tenant_status", "tenant_id", "status"),
        Index("idx_alerts_fingerprint_status", "fingerprint", "status"),
    )
