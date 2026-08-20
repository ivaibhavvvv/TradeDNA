import uuid
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.tenant import Tenant
    from src.models.session import UserSession, RefreshToken
    from src.models.audit import AuditLog


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="users",
        lazy="selectin",
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="user",
        cascade="all, delete-orphan",
    )
