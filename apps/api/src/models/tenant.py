import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.user import User
    from src.models.audit import AuditLog


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_tier: Mapped[str] = mapped_column(String(50), nullable=False, default="starter")

    # Relationships
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
