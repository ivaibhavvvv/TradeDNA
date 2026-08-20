from datetime import datetime, timezone
from typing import Optional
import uuid
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, UUIDPrimaryKeyMixin


class AccountDisplaySetting(Base, UUIDPrimaryKeyMixin):
    """User-customized presentation metadata for an authorized Exness account."""

    __tablename__ = "account_display_settings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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

    __table_args__ = (
        UniqueConstraint("tenant_id", "account_number", name="uq_tenant_account_display"),
    )
