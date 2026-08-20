import uuid
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.tenant import Tenant
    from src.models.user import User


class AuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_logs"

    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False, default="")
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(
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

    # Relationships
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant", back_populates="audit_logs")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")
