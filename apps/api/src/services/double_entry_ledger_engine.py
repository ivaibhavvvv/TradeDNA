"""TradeDNA Phase 5 - Double-Entry Ledger Engine
Constructs formal double-entry financial transactions and postings.
Enforces the mandatory invariant: SUM(debits) == SUM(credits) on every transaction.
Provides deterministic running balance projections over the ledger posting stream.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.exceptions import ValidationException
from src.models.canonical_ledger import (
    CanonicalBalanceEvent,
    CanonicalLedgerPosting,
    CanonicalLedgerTransaction,
    CanonicalTrade,
)


class UnbalancedLedgerTransactionException(ValidationException):
    """Raised when a double-entry transaction has fewer than 2 postings or debits != credits."""
    pass


class DoubleEntryLedgerEngine:
    """Core engine for recording double-entry ledger journals and validating balance invariants."""

    @classmethod
    def validate_and_create_transaction(
        cls,
        tenant_id: uuid.UUID,
        reconstruction_run_id: uuid.UUID,
        account_number: int,
        transaction_type: str,
        transaction_time_msc: int,
        transaction_timestamp_utc: datetime,
        description: str,
        source_observation_id: uuid.UUID,
        postings: list[dict],
        trade_id: Optional[uuid.UUID] = None,
        execution_id: Optional[uuid.UUID] = None,
        balance_event_id: Optional[uuid.UUID] = None,
    ) -> tuple[CanonicalLedgerTransaction, list[CanonicalLedgerPosting]]:
        """Validates that postings balance (SUM(debits) == SUM(credits)) and builds the transaction."""
        if len(postings) < 2:
            raise UnbalancedLedgerTransactionException(
                f"Double-entry transaction requires at least 2 postings, got {len(postings)}"
            )

        total_debit = Decimal("0.0000")
        total_credit = Decimal("0.0000")

        for p in postings:
            deb = Decimal(str(p.get("debit", "0.0000"))).quantize(Decimal("0.0001"))
            cred = Decimal(str(p.get("credit", "0.0000"))).quantize(Decimal("0.0001"))

            if (deb > 0 and cred > 0) or (deb == 0 and cred == 0):
                raise UnbalancedLedgerTransactionException(
                    f"Posting must have either debit > 0 or credit > 0, got debit={deb}, credit={cred}"
                )

            total_debit += deb
            total_credit += cred

        if total_debit != total_credit:
            raise UnbalancedLedgerTransactionException(
                f"Unbalanced double-entry transaction: total_debit={total_debit} != total_credit={total_credit}"
            )

        tx_id = uuid.uuid4()
        tx = CanonicalLedgerTransaction(
            id=tx_id,
            tenant_id=tenant_id,
            reconstruction_run_id=reconstruction_run_id,
            account_number=account_number,
            trade_id=trade_id,
            execution_id=execution_id,
            balance_event_id=balance_event_id,
            source_observation_id=source_observation_id,
            transaction_type=transaction_type,
            transaction_time_msc=transaction_time_msc,
            transaction_timestamp_utc=transaction_timestamp_utc,
            description=description,
        )

        db_postings = []
        for p in postings:
            deb = Decimal(str(p.get("debit", "0.0000"))).quantize(Decimal("0.0001"))
            cred = Decimal(str(p.get("credit", "0.0000"))).quantize(Decimal("0.0001"))
            db_postings.append(
                CanonicalLedgerPosting(
                    id=uuid.uuid4(),
                    transaction_id=tx_id,
                    account_type=p["account_type"],
                    debit_amount=deb,
                    credit_amount=cred,
                    currency=p.get("currency", "USD"),
                )
            )

        return tx, db_postings

    @classmethod
    def build_trade_settlement_postings(
        cls,
        trade: CanonicalTrade,
        currency: str = "USD",
    ) -> list[dict]:
        """Builds balanced double-entry posting dicts for a realized trade closure."""
        postings: list[dict] = []

        # 1. Realized Gross P&L
        if trade.realized_gross_pnl > Decimal("0.0000"):
            # Profit: Debit Cash, Credit Realized PnL
            postings.append({"account_type": "CASH_BALANCE", "debit": trade.realized_gross_pnl, "credit": Decimal("0"), "currency": currency})
            postings.append({"account_type": "REALIZED_PNL", "debit": Decimal("0"), "credit": trade.realized_gross_pnl, "currency": currency})
        elif trade.realized_gross_pnl < Decimal("0.0000"):
            # Loss: Debit Realized PnL, Credit Cash
            loss_abs = abs(trade.realized_gross_pnl)
            postings.append({"account_type": "REALIZED_PNL", "debit": loss_abs, "credit": Decimal("0"), "currency": currency})
            postings.append({"account_type": "CASH_BALANCE", "debit": Decimal("0"), "credit": loss_abs, "currency": currency})

        # 2. Commission Expense (Fee paid reduces cash)
        if trade.total_commission != Decimal("0.0000"):
            comm_abs = abs(trade.total_commission)
            postings.append({"account_type": "COMMISSION_EXPENSE", "debit": comm_abs, "credit": Decimal("0"), "currency": currency})
            postings.append({"account_type": "CASH_BALANCE", "debit": Decimal("0"), "credit": comm_abs, "currency": currency})

        # 3. Swap (Financing charge or credit)
        if trade.total_swap < Decimal("0.0000"):
            # Negative swap reduces cash
            swap_abs = abs(trade.total_swap)
            postings.append({"account_type": "SWAP_EXPENSE", "debit": swap_abs, "credit": Decimal("0"), "currency": currency})
            postings.append({"account_type": "CASH_BALANCE", "debit": Decimal("0"), "credit": swap_abs, "currency": currency})
        elif trade.total_swap > Decimal("0.0000"):
            # Positive swap increases cash
            postings.append({"account_type": "CASH_BALANCE", "debit": trade.total_swap, "credit": Decimal("0"), "currency": currency})
            postings.append({"account_type": "SWAP_EXPENSE", "debit": Decimal("0"), "credit": trade.total_swap, "currency": currency})

        # 4. Broker Fees
        if trade.total_fees != Decimal("0.0000"):
            fee_abs = abs(trade.total_fees)
            postings.append({"account_type": "BROKER_FEE_EXPENSE", "debit": fee_abs, "credit": Decimal("0"), "currency": currency})
            postings.append({"account_type": "CASH_BALANCE", "debit": Decimal("0"), "credit": fee_abs, "currency": currency})

        # If zero P&L and zero fees (rare exact breakeven fill)
        if not postings:
            postings.append({"account_type": "CASH_BALANCE", "debit": Decimal("0.0001"), "credit": Decimal("0"), "currency": currency})
            postings.append({"account_type": "REALIZED_PNL", "debit": Decimal("0"), "credit": Decimal("0.0001"), "currency": currency})

        return postings

    @classmethod
    def build_balance_event_postings(
        cls,
        event_type: str,
        amount: Decimal,
        currency: str = "USD",
    ) -> list[dict]:
        """Builds balanced double-entry posting dicts for non-trading balance events."""
        postings: list[dict] = []
        amt_abs = abs(amount)

        if event_type == "DEPOSIT":
            postings.append({"account_type": "CASH_BALANCE", "debit": amt_abs, "credit": Decimal("0"), "currency": currency})
            postings.append({"account_type": "DEPOSIT_EQUITY", "debit": Decimal("0"), "credit": amt_abs, "currency": currency})
        elif event_type == "WITHDRAWAL":
            postings.append({"account_type": "WITHDRAWAL_EQUITY", "debit": amt_abs, "credit": Decimal("0"), "currency": currency})
            postings.append({"account_type": "CASH_BALANCE", "debit": Decimal("0"), "credit": amt_abs, "currency": currency})
        elif event_type == "CREDIT":
            postings.append({"account_type": "CREDIT_FACILITY", "debit": amt_abs, "credit": Decimal("0"), "currency": currency})
            postings.append({"account_type": "DEPOSIT_EQUITY", "debit": Decimal("0"), "credit": amt_abs, "currency": currency})
        elif event_type == "DIVIDEND":
            postings.append({"account_type": "CASH_BALANCE", "debit": amt_abs, "credit": Decimal("0"), "currency": currency})
            postings.append({"account_type": "DIVIDEND_INCOME", "debit": Decimal("0"), "credit": amt_abs, "currency": currency})
        elif event_type == "TAX":
            postings.append({"account_type": "TAX_EXPENSE", "debit": amt_abs, "credit": Decimal("0"), "currency": currency})
            postings.append({"account_type": "CASH_BALANCE", "debit": Decimal("0"), "credit": amt_abs, "currency": currency})
        elif event_type == "CORRECTION":
            if amount >= Decimal("0"):
                postings.append({"account_type": "CASH_BALANCE", "debit": amt_abs, "credit": Decimal("0"), "currency": currency})
                postings.append({"account_type": "DEPOSIT_EQUITY", "debit": Decimal("0"), "credit": amt_abs, "currency": currency})
            else:
                postings.append({"account_type": "WITHDRAWAL_EQUITY", "debit": amt_abs, "credit": Decimal("0"), "currency": currency})
                postings.append({"account_type": "CASH_BALANCE", "debit": Decimal("0"), "credit": amt_abs, "currency": currency})
        else:
            # Default / Fee fallback
            postings.append({"account_type": "BROKER_FEE_EXPENSE", "debit": amt_abs, "credit": Decimal("0"), "currency": currency})
            postings.append({"account_type": "CASH_BALANCE", "debit": Decimal("0"), "credit": amt_abs, "currency": currency})

        return postings

    @classmethod
    async def get_running_balance_projection(
        cls,
        session: AsyncSession,
        reconstruction_run_id: uuid.UUID,
        account_number: int,
    ) -> Decimal:
        """Computes authoritative derived running cash balance from the ordered ledger postings."""
        stmt = (
            select(
                func.coalesce(func.sum(CanonicalLedgerPosting.debit_amount), Decimal("0")) -
                func.coalesce(func.sum(CanonicalLedgerPosting.credit_amount), Decimal("0"))
            )
            .join(CanonicalLedgerTransaction, CanonicalLedgerPosting.transaction_id == CanonicalLedgerTransaction.id)
            .where(
                CanonicalLedgerTransaction.reconstruction_run_id == reconstruction_run_id,
                CanonicalLedgerTransaction.account_number == account_number,
                CanonicalLedgerPosting.account_type == "CASH_BALANCE",
            )
        )
        res = await session.execute(stmt)
        return (res.scalar() or Decimal("0.0000")).quantize(Decimal("0.0001"))
