from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional
import uuid
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, UUIDPrimaryKeyMixin


class OnboardingProgress(Base, UUIDPrimaryKeyMixin):
    """Tracks persistent, resumable SaaS onboarding progress per tenant/user."""

    __tablename__ = "onboarding_progress"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    current_step: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="REGISTERED",
    )
    # REGISTERED, EMAIL_VERIFICATION_PENDING, EMAIL_VERIFIED,
    # WORKSPACE_CONFIGURED, AWAITING_CONNECTOR_HANDSHAKE,
    # INITIAL_SYNC_IN_PROGRESS, DATA_VALIDATED, COMPLETED

    is_completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    email_verification_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    email_verification_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    workspace_name: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    default_currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="USD",
    )

    paired_account_number: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )
    paired_device_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
    )

    initial_sync_deal_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    initial_integrity_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )
    step_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
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

    # Relationships
    tenant = relationship("Tenant", lazy="selectin")
    user = relationship("User", lazy="selectin")
    paired_device = relationship("Device", lazy="selectin")
