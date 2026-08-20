from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import uuid
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, UUIDPrimaryKeyMixin


class CanonicalExecution(Base, UUIDPrimaryKeyMixin):
    """Normalized trading fill execution preserving MT5 identifiers and CLOSE_BY counter lineage."""

    __tablename__ = "canonical_executions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reconstruction_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconstruction_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("raw_event_observations.observation_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    ingress_payload_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("raw_ingress_payloads.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY, SELL
    entry_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # ENTRY_IN, ENTRY_OUT, ENTRY_INOUT, ENTRY_OUT_BY
    volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    matched_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    deal_ticket: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    order_ticket: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    position_ticket: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, index=True)
    counter_position_ticket: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    counter_deal_ticket: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    gross_profit: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    swap: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    fee: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    execution_time_msc: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    execution_timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("reconstruction_run_id", "account_number", "deal_ticket", name="uq_canonical_exec_run"),
        Index("idx_can_exec_replay", "reconstruction_run_id", "account_number", "symbol", "execution_time_msc", "deal_ticket"),
        Index("idx_can_exec_pos_ticket", "reconstruction_run_id", "account_number", "position_ticket"),
    )


class CanonicalTrade(Base, UUIDPrimaryKeyMixin):
    """Reconstructed round-trip trade with deterministic versioning and lineage."""

    __tablename__ = "canonical_trades"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reconstruction_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconstruction_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY (Long), SELL (Short)
    account_mode: Mapped[str] = mapped_column(String(16), nullable=False)  # HEDGING, NETTING
    position_ticket: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    total_entry_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    total_exit_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    open_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    vwap_entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    vwap_exit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    realized_gross_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    total_commission: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    total_swap: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    total_fees: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    realized_net_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    trade_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="OPEN",
    )  # OPEN, PARTIALLY_CLOSED, CLOSED, REVERSED, UNMATCHED, CONFLICTED, SUPERSEDED
    opened_at_msc: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    opened_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at_msc: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    closed_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("canonical_trades.id", ondelete="SET NULL"),
        nullable=True,
    )
    supersedes_trade_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("canonical_trades.id", ondelete="SET NULL"),
        nullable=True,
    )
    superseded_by_trade_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("canonical_trades.id", ondelete="SET NULL"),
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

    __table_args__ = (
        Index("idx_can_trades_lookup", "reconstruction_run_id", "account_number", "symbol", "trade_status"),
        Index("idx_can_trades_time", "reconstruction_run_id", "account_number", "opened_at_msc", "closed_at_msc"),
    )


class CanonicalTradeExecutionMap(Base, UUIDPrimaryKeyMixin):
    """Lot-by-lot execution matching record defining authoritative cost basis and realized P&L."""

    __tablename__ = "canonical_trade_execution_map"

    trade_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("canonical_trades.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_execution_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("canonical_executions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    exit_execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("canonical_executions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    matched_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    exit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    realized_gross_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    attributed_commission: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    attributed_swap: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    attributed_fee: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_map_trade_id", "trade_id"),
        Index("idx_map_entry_exec", "entry_execution_id"),
        Index("idx_map_exit_exec", "exit_execution_id"),
    )


class CanonicalBalanceEvent(Base, UUIDPrimaryKeyMixin):
    """Normalized non-trading financial transaction (deposit, withdrawal, credit, tax, dividend)."""

    __tablename__ = "canonical_balance_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reconstruction_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconstruction_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("raw_event_observations.observation_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    ingress_payload_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("raw_ingress_payloads.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )  # DEPOSIT, WITHDRAWAL, CREDIT, FEE, CORRECTION, DIVIDEND, TAX, COMMISSION_ADJUSTMENT
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    deal_ticket: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_time_msc: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    event_timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("reconstruction_run_id", "account_number", "deal_ticket", name="uq_canonical_bal_run"),
        Index("idx_can_bal_time", "reconstruction_run_id", "account_number", "event_time_msc"),
    )


class CanonicalLedgerTransaction(Base, UUIDPrimaryKeyMixin):
    """Header record for a balanced double-entry financial transaction."""

    __tablename__ = "canonical_ledger_transactions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reconstruction_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reconstruction_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    trade_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("canonical_trades.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("canonical_executions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    balance_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("canonical_balance_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_observation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("raw_event_observations.observation_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    transaction_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )  # TRADE_SETTLEMENT, COMMISSION_CHARGE, SWAP_CHARGE, CASH_DEPOSIT, CASH_WITHDRAWAL, CREDIT_ISSUANCE, DIVIDEND_SETTLEMENT, TAX_WITHHOLDING, CORRECTION_SETTLEMENT
    transaction_time_msc: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    transaction_timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_can_ledger_tx", "reconstruction_run_id", "account_number", "transaction_time_msc", "id"),
    )


class CanonicalLedgerPosting(Base, UUIDPrimaryKeyMixin):
    """Line-item debit/credit posting belonging to a double-entry transaction."""

    __tablename__ = "canonical_ledger_postings"

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("canonical_ledger_transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )  # CASH_BALANCE, REALIZED_PNL, COMMISSION_EXPENSE, SWAP_EXPENSE, BROKER_FEE_EXPENSE, DEPOSIT_EQUITY, WITHDRAWAL_EQUITY, CREDIT_FACILITY, TAX_EXPENSE, DIVIDEND_INCOME
    debit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    credit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint(
            "(debit_amount > 0 AND credit_amount = 0) OR (credit_amount > 0 AND debit_amount = 0)",
            name="chk_debit_or_credit",
        ),
        Index("idx_can_postings_tx", "transaction_id", "account_type"),
    )
