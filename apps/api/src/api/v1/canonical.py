"""TradeDNA Phase 5 - Canonical Ledger & Trade Reconstruction API Router"""

from typing import Any, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db_session
from src.core.dependencies import get_current_user
from src.models.canonical_ledger import (
    CanonicalExecution,
    CanonicalLedgerPosting,
    CanonicalLedgerTransaction,
    CanonicalTrade,
    CanonicalTradeExecutionMap,
)
from src.models.reconstruction_run import ReconstructionRun
from src.models.sync_state import AccountSyncState
from src.models.user import User
from src.services.double_entry_ledger_engine import DoubleEntryLedgerEngine
from src.services.reconstruction_manager import ReconstructionManager

router = APIRouter()


@router.get("/trades/{account_number}", status_code=status.HTTP_200_OK)
async def get_canonical_trades(
    account_number: int,
    symbol: Optional[str] = None,
    trade_status: Optional[str] = None,
    run_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Returns canonical trades for an account from the active or specified reconstruction run."""
    # Resolve target run_id
    if not run_id:
        stmt_sync = select(AccountSyncState).where(
            AccountSyncState.tenant_id == current_user.tenant_id,
            AccountSyncState.account_number == account_number,
        )
        res_sync = await db.execute(stmt_sync)
        sync_state = res_sync.scalars().first()
        if not sync_state or not sync_state.active_reconstruction_run_id:
            return {"account_number": account_number, "run_id": None, "trades": []}
        target_run_id = sync_state.active_reconstruction_run_id
    else:
        target_run_id = run_id

    stmt = select(CanonicalTrade).where(
        CanonicalTrade.tenant_id == current_user.tenant_id,
        CanonicalTrade.account_number == account_number,
        CanonicalTrade.reconstruction_run_id == target_run_id,
    )
    if symbol:
        stmt = stmt.where(CanonicalTrade.symbol == symbol.upper().strip())
    if trade_status:
        stmt = stmt.where(CanonicalTrade.trade_status == trade_status.upper().strip())

    stmt = stmt.order_by(CanonicalTrade.opened_at_msc.asc(), CanonicalTrade.position_ticket.asc())
    res = await db.execute(stmt)
    trades = res.scalars().all()

    return {
        "account_number": account_number,
        "run_id": str(target_run_id),
        "total_trades": len(trades),
        "trades": [
            {
                "id": str(t.id),
                "symbol": t.symbol,
                "side": t.side,
                "account_mode": t.account_mode,
                "position_ticket": t.position_ticket,
                "total_entry_volume": str(t.total_entry_volume),
                "total_exit_volume": str(t.total_exit_volume),
                "open_volume": str(t.open_volume),
                "vwap_entry_price": str(t.vwap_entry_price),
                "vwap_exit_price": str(t.vwap_exit_price) if t.vwap_exit_price is not None else None,
                "realized_gross_pnl": str(t.realized_gross_pnl),
                "total_commission": str(t.total_commission),
                "total_swap": str(t.total_swap),
                "total_fees": str(t.total_fees),
                "realized_net_pnl": str(t.realized_net_pnl),
                "trade_status": t.trade_status,
                "opened_at_utc": t.opened_at_utc.isoformat(),
                "closed_at_utc": t.closed_at_utc.isoformat() if t.closed_at_utc else None,
                "duration_seconds": t.duration_seconds,
                "version": t.version,
            }
            for t in trades
        ],
    }


@router.get("/ledger/{account_number}", status_code=status.HTTP_200_OK)
async def get_canonical_ledger(
    account_number: int,
    run_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Returns double-entry ledger transactions and derived running balance projection."""
    if not run_id:
        stmt_sync = select(AccountSyncState).where(
            AccountSyncState.tenant_id == current_user.tenant_id,
            AccountSyncState.account_number == account_number,
        )
        res_sync = await db.execute(stmt_sync)
        sync_state = res_sync.scalars().first()
        if not sync_state or not sync_state.active_reconstruction_run_id:
            return {"account_number": account_number, "run_id": None, "running_balance": "0.0000", "transactions": []}
        target_run_id = sync_state.active_reconstruction_run_id
    else:
        target_run_id = run_id

    running_balance = await DoubleEntryLedgerEngine.get_running_balance_projection(
        session=db,
        reconstruction_run_id=target_run_id,
        account_number=account_number,
    )

    stmt_tx = select(CanonicalLedgerTransaction).where(
        CanonicalLedgerTransaction.tenant_id == current_user.tenant_id,
        CanonicalLedgerTransaction.account_number == account_number,
        CanonicalLedgerTransaction.reconstruction_run_id == target_run_id,
    ).order_by(CanonicalLedgerTransaction.transaction_time_msc.asc(), CanonicalLedgerTransaction.id.asc())

    res_tx = await db.execute(stmt_tx)
    transactions = list(res_tx.scalars().all())

    return {
        "account_number": account_number,
        "run_id": str(target_run_id),
        "running_balance": str(running_balance),
        "transactions_count": len(transactions),
        "transactions": [
            {
                "id": str(tx.id),
                "transaction_type": tx.transaction_type,
                "transaction_time_msc": tx.transaction_time_msc,
                "transaction_timestamp_utc": tx.transaction_timestamp_utc.isoformat(),
                "description": tx.description,
                "trade_id": str(tx.trade_id) if tx.trade_id else None,
                "execution_id": str(tx.execution_id) if tx.execution_id else None,
                "balance_event_id": str(tx.balance_event_id) if tx.balance_event_id else None,
            }
            for tx in transactions
        ],
    }


@router.post("/reconstruct/{account_number}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_reconstruction(
    account_number: int,
    reason: str = Query(default="MANUAL_REQUEST"),
    auto_activate: bool = Query(default=True),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Triggers an isolated reconstruction run from Phase 4 Layer 1 observations."""
    run, trades = await ReconstructionManager.execute_reconstruction(
        session=db,
        tenant_id=current_user.tenant_id,
        account_number=account_number,
        reason=reason,
        auto_activate=auto_activate,
    )
    await db.commit()
    return {
        "run_id": str(run.id),
        "run_number": run.run_number,
        "status": run.status,
        "reconstructed_trades_count": len(trades),
        "reason": run.reason,
    }


@router.post("/runs/{account_number}/switch", status_code=status.HTTP_200_OK)
async def switch_active_reconstruction_run(
    account_number: int,
    target_run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Atomically switches the active reconstruction version set for an account."""
    target_run = await ReconstructionManager.switch_active_run(
        session=db,
        tenant_id=current_user.tenant_id,
        account_number=account_number,
        target_run_id=target_run_id,
    )
    await db.commit()
    return {
        "account_number": account_number,
        "active_run_id": str(target_run.id),
        "run_number": target_run.run_number,
        "status": target_run.status,
    }


@router.get("/runs/{account_number}", status_code=status.HTTP_200_OK)
async def list_reconstruction_runs(
    account_number: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Lists all reconstruction runs for an account."""
    stmt = select(ReconstructionRun).where(
        ReconstructionRun.tenant_id == current_user.tenant_id,
        ReconstructionRun.account_number == account_number,
    ).order_by(ReconstructionRun.run_number.desc())

    res = await db.execute(stmt)
    runs = res.scalars().all()
    return {
        "account_number": account_number,
        "runs": [
            {
                "id": str(r.id),
                "run_number": r.run_number,
                "status": r.status,
                "reason": r.reason,
                "started_at": r.started_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "active_at": r.active_at.isoformat() if r.active_at else None,
                "error_details": r.error_details,
            }
            for r in runs
        ],
    }
