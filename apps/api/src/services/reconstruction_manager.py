"""TradeDNA Phase 5 - Reconstruction Manager
Manages isolated reconstruction runs, cold replay rebuilding from Layer 1,
atomic active-version switching, run comparison, and rollback operations.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import uuid
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.exceptions import NotFoundException, ValidationException
from src.models.canonical_ledger import CanonicalExecution, CanonicalTrade
from src.models.raw_event import RawEventObservation
from src.models.reconstruction_run import ReconstructionRun
from src.models.sync_state import AccountSyncState
from src.services.trade_reconstruction_engine import TradeReconstructionEngine


class ReconstructionManager:
    """Orchestrator for deterministic reconstruction runs and active version sets."""

    @classmethod
    async def create_run(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
        server_name: str,
        reason: str = "INITIAL_INGESTION",
    ) -> ReconstructionRun:
        """Creates a new isolated ReconstructionRun record."""
        # Calculate next run_number
        stmt = select(func.coalesce(func.max(ReconstructionRun.run_number), 0)).where(
            ReconstructionRun.tenant_id == tenant_id,
            ReconstructionRun.account_number == account_number,
        )
        res = await session.execute(stmt)
        next_run_num = res.scalar() + 1

        run = ReconstructionRun(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            account_number=account_number,
            server_name=server_name,
            run_number=next_run_num,
            status="RUNNING",
            reason=reason,
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.flush()
        return run

    @classmethod
    async def execute_reconstruction(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
        reason: str = "INITIAL_INGESTION",
        auto_activate: bool = True,
    ) -> tuple[ReconstructionRun, list[CanonicalTrade]]:
        """Executes a complete reconstruction from Phase 4 Layer 1 raw observations."""
        # Fetch account sync state to get server_name, trade_mode, currency
        stmt_sync = select(AccountSyncState).where(
            AccountSyncState.tenant_id == tenant_id,
            AccountSyncState.account_number == account_number,
        )
        res_sync = await session.execute(stmt_sync)
        sync_state = res_sync.scalars().first()
        if not sync_state:
            raise NotFoundException(f"Account sync state for account #{account_number} not found.")

        # Create isolated run
        run = await cls.create_run(
            session=session,
            tenant_id=tenant_id,
            account_number=account_number,
            server_name=sync_state.server_name,
            reason=reason,
        )

        try:
            # Query all Layer 1 raw observations for this account
            stmt_obs = select(RawEventObservation).where(
                RawEventObservation.tenant_id == tenant_id,
                RawEventObservation.account_number == account_number,
            ).order_by(RawEventObservation.source_time_msc.asc(), RawEventObservation.external_ticket.asc())

            res_obs = await session.execute(stmt_obs)
            raw_observations = list(res_obs.scalars().all())

            # Reconstruct trades and ledger
            trades, _, _ = await TradeReconstructionEngine.process_raw_observations_for_run(
                session=session,
                tenant_id=tenant_id,
                account_number=account_number,
                server_name=sync_state.server_name,
                account_mode=sync_state.trade_mode if sync_state.trade_mode in ("HEDGING", "NETTING") else "HEDGING",
                account_currency=sync_state.currency,
                reconstruction_run=run,
                raw_observations=raw_observations,
            )

            run.status = "ACTIVE" if auto_activate else "COMPLETED"
            run.completed_at = datetime.now(timezone.utc)
            if auto_activate:
                run.active_at = datetime.now(timezone.utc)
                sync_state.active_reconstruction_run_id = run.id

            await session.flush()
            return run, trades

        except Exception as ex:
            run.status = "FAILED"
            run.error_details = str(ex)
            run.completed_at = datetime.now(timezone.utc)
            await session.flush()
            raise

    @classmethod
    async def switch_active_run(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
        target_run_id: uuid.UUID,
    ) -> ReconstructionRun:
        """Atomically switches the active reconstruction run pointer for an account."""
        stmt_run = select(ReconstructionRun).where(
            ReconstructionRun.id == target_run_id,
            ReconstructionRun.tenant_id == tenant_id,
            ReconstructionRun.account_number == account_number,
        )
        res_run = await session.execute(stmt_run)
        target_run = res_run.scalars().first()
        if not target_run:
            raise NotFoundException(f"Reconstruction run {target_run_id} not found for account #{account_number}.")

        if target_run.status not in ("ACTIVE", "COMPLETED", "SUPERSEDED"):
            raise ValidationException(f"Cannot activate reconstruction run in status '{target_run.status}'.")

        # Mark prior active runs as SUPERSEDED
        stmt_prior = (
            update(ReconstructionRun)
            .where(
                ReconstructionRun.tenant_id == tenant_id,
                ReconstructionRun.account_number == account_number,
                ReconstructionRun.status == "ACTIVE",
                ReconstructionRun.id != target_run_id,
            )
            .values(status="SUPERSEDED")
        )
        await session.execute(stmt_prior)

        target_run.status = "ACTIVE"
        target_run.active_at = datetime.now(timezone.utc)

        # Update account sync state pointer
        stmt_sync = (
            update(AccountSyncState)
            .where(
                AccountSyncState.tenant_id == tenant_id,
                AccountSyncState.account_number == account_number,
            )
            .values(active_reconstruction_run_id=target_run.id)
        )
        await session.execute(stmt_sync)
        await session.flush()
        return target_run

    @classmethod
    async def compare_runs(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
        run_id_a: uuid.UUID,
        run_id_b: uuid.UUID,
    ) -> dict:
        """Compares high-level metrics between two reconstruction runs."""
        async def _get_run_summary(run_id: uuid.UUID) -> dict:
            stmt = select(
                func.count(CanonicalTrade.id),
                func.coalesce(func.sum(CanonicalTrade.realized_gross_pnl), Decimal("0")),
                func.coalesce(func.sum(CanonicalTrade.total_commission), Decimal("0")),
                func.coalesce(func.sum(CanonicalTrade.total_swap), Decimal("0")),
                func.coalesce(func.sum(CanonicalTrade.realized_net_pnl), Decimal("0")),
                func.coalesce(func.sum(CanonicalTrade.total_entry_volume), Decimal("0")),
            ).where(
                CanonicalTrade.tenant_id == tenant_id,
                CanonicalTrade.reconstruction_run_id == run_id,
            )
            res = await session.execute(stmt)
            row = res.first()
            return {
                "trades_count": row[0],
                "total_gross_pnl": str(row[1]),
                "total_commission": str(row[2]),
                "total_swap": str(row[3]),
                "total_net_pnl": str(row[4]),
                "total_volume": str(row[5]),
            }

        summary_a = await _get_run_summary(run_id_a)
        summary_b = await _get_run_summary(run_id_b)

        return {
            "account_number": account_number,
            "run_a": {"id": str(run_id_a), **summary_a},
            "run_b": {"id": str(run_id_b), **summary_b},
        }
