from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import uuid
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, UUIDPrimaryKeyMixin


class InstrumentSpecification(Base, UUIDPrimaryKeyMixin):
    """Immutable specification snapshot for a trading symbol (contract size, tick value, mode)."""

    __tablename__ = "instrument_specifications"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    contract_size: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tick_size: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    tick_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    digits: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    base_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    profit_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    calculation_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="FOREX",
    )  # FOREX, CFD, FUTURES, EXCHANGE, CRYPTO
    effective_from_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "symbol", "effective_from_utc", name="uq_inst_spec_timeline"),
        Index("idx_inst_spec_lookup", "tenant_id", "symbol", "effective_from_utc", "effective_to_utc"),
    )


class HistoricalExchangeRate(Base, UUIDPrimaryKeyMixin):
    """Historical currency conversion rate snapshot for multi-currency settlement."""

    __tablename__ = "historical_exchange_rates"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    base_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    effective_time_msc: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    effective_timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "base_currency", "quote_currency", "effective_time_msc", name="uq_hist_fx_rate"),
        Index("idx_hist_fx_lookup", "tenant_id", "base_currency", "quote_currency", "effective_time_msc"),
    )
