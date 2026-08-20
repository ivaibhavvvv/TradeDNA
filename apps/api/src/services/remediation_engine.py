"""TradeDNA Phase 6 - Controlled Remediation State Machine Engine
Executes non-destructive remediation workflows:
DETECTED -> CLASSIFIED -> REMEDIATION_PROPOSED -> REMEDIATION_APPROVED ->
REMEDIATION_EXECUTING -> VALIDATING -> RESOLVED (or FAILED / REJECTED).
Zero mutation of existing raw observations or canonical records.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.raw_event import RawEventObservation
from src.models.reconciliation import (
    ReconciliationDiscrepancy,
    ReconciliationRun,
    RemediationProposal,
)
from src.models.reconstruction_run import ReconstructionRun
from src.models.sync_state import AccountSyncState
from src.services.reconciliation_engine import ReconciliationEngine
from src.services.reconstruction_manager import ReconstructionManager
from src.services.trade_reconstruction_engine import TradeReconstructionEngine


class RemediationAuthorizationError(Exception):
    """Raised when an unauthorized entity attempts to approve or execute remediation."""


class RemediationExecutionError(Exception):
    """Raised when remediation execution or validation fails."""


class RemediationEngine:
    """Non-destructive controlled remediation pipeline with atomic promotion gates."""

    VALID_TRANSITIONS = {
        "DETECTED": ["CLASSIFIED", "REMEDIATION_PROPOSED", "REJECTED"],
        "CLASSIFIED": ["REMEDIATION_PROPOSED", "REJECTED"],
        "REMEDIATION_PROPOSED": ["REMEDIATION_APPROVED", "REJECTED"],
        "REMEDIATION_APPROVED": ["REMEDIATION_EXECUTING", "REJECTED"],
        "REMEDIATION_EXECUTING": ["VALIDATING", "FAILED"],
        "VALIDATING": ["RESOLVED", "FAILED"],
        "RESOLVED": [],
        "FAILED": ["REMEDIATION_PROPOSED", "REJECTED"],
        "REJECTED": [],
    }

    @classmethod
    async def create_proposal(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
        server_name: str,
        proposal_type: str,  # TRIGGER_RECONSTRUCTION_REBUILD, BACKFILL_RAW_INGRESS, EXPLAIN_BROKER_ANOMALY
        discrepancy_id: Optional[uuid.UUID] = None,
        proposed_action: Optional[dict[str, Any]] = None,
    ) -> RemediationProposal:
        """Creates a remediation proposal in REMEDIATION_PROPOSED state."""
        proposal = RemediationProposal(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            account_number=account_number,
            server_name=server_name,
            discrepancy_id=discrepancy_id,
            proposal_type=proposal_type,
            status="REMEDIATION_PROPOSED",
            proposed_action=proposed_action or {},
            execution_result={},
        )
        session.add(proposal)

        if discrepancy_id:
            stmt_d = select(ReconciliationDiscrepancy).where(
                ReconciliationDiscrepancy.tenant_id == tenant_id,
                ReconciliationDiscrepancy.id == discrepancy_id,
            )
            res_d = await session.execute(stmt_d)
            disc = res_d.scalar_one_or_none()
            if disc:
                disc.remediation_proposal_id = proposal.id
                disc.status = "REMEDIATION_PROPOSED"

        await session.flush()
        return proposal

    @classmethod
    async def approve_proposal(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        proposal_id: uuid.UUID,
        approved_by_user_id: uuid.UUID,
    ) -> RemediationProposal:
        """Approves a remediation proposal."""
        stmt = select(RemediationProposal).where(
            RemediationProposal.tenant_id == tenant_id,
            RemediationProposal.id == proposal_id,
        )
        res = await session.execute(stmt)
        proposal = res.scalar_one_or_none()
        if not proposal:
            raise RemediationAuthorizationError("Proposal not found or tenant access denied.")

        if proposal.status not in ("REMEDIATION_PROPOSED", "CLASSIFIED", "DETECTED"):
            raise RemediationAuthorizationError(f"Cannot approve proposal in status: {proposal.status}")

        proposal.status = "REMEDIATION_APPROVED"
        proposal.approved_by = approved_by_user_id
        proposal.approved_at = datetime.now(timezone.utc)
        await session.flush()
        return proposal

    @classmethod
    async def execute_remediation(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        proposal_id: uuid.UUID,
    ) -> tuple[RemediationProposal, Optional[ReconciliationRun]]:
        """Executes non-destructive remediation:
        1. Spawns a NEW draft reconstruction run (zero mutation of active run).
        2. Re-runs reconstruction.
        3. Spawns a new reconciliation run to validate.
        4. Atomically promotes the new run ONLY if validation passes.
        """
        stmt = select(RemediationProposal).where(
            RemediationProposal.tenant_id == tenant_id,
            RemediationProposal.id == proposal_id,
        )
        res = await session.execute(stmt)
        proposal = res.scalar_one_or_none()
        if not proposal:
            raise RemediationAuthorizationError("Proposal not found or tenant access denied.")

        if proposal.status != "REMEDIATION_APPROVED":
            raise RemediationAuthorizationError(f"Proposal must be REMEDIATION_APPROVED to execute. Current: {proposal.status}")

        proposal.status = "REMEDIATION_EXECUTING"
        proposal.executed_at = datetime.now(timezone.utc)
        await session.flush()

        try:
            # Fetch sync state to get account configuration
            stmt_s = select(AccountSyncState).where(
                AccountSyncState.tenant_id == tenant_id,
                AccountSyncState.account_number == proposal.account_number,
                AccountSyncState.server_name == proposal.server_name,
            )
            res_s = await session.execute(stmt_s)
            sync_state = res_s.scalar_one_or_none()
            account_mode = sync_state.trade_mode if (sync_state and sync_state.trade_mode in ("HEDGING", "NETTING")) else "HEDGING"
            account_currency = sync_state.currency if sync_state else "USD"

            # 1. Create a NEW isolated Draft Reconstruction Run
            new_recon_run = await ReconstructionManager.create_run(
                session=session,
                tenant_id=tenant_id,
                account_number=proposal.account_number,
                server_name=proposal.server_name,
                reason=f"REMEDIATION_FOR_PROPOSAL_{proposal.id}",
            )
            proposal.new_reconstruction_run_id = new_recon_run.id

            # 2. Fetch all raw observations for account
            stmt_obs = select(RawEventObservation).where(
                RawEventObservation.tenant_id == tenant_id,
                RawEventObservation.account_number == proposal.account_number,
            )
            res_obs = await session.execute(stmt_obs)
            raw_observations = list(res_obs.scalars().all())

            # 3. Process new reconstruction run
            await TradeReconstructionEngine.process_raw_observations_for_run(
                session=session,
                tenant_id=tenant_id,
                account_number=proposal.account_number,
                server_name=proposal.server_name,
                account_mode=account_mode,
                account_currency=account_currency,
                reconstruction_run=new_recon_run,
                raw_observations=raw_observations,
            )
            new_recon_run.status = "COMPLETED"
            new_recon_run.completed_at = datetime.now(timezone.utc)

            proposal.status = "VALIDATING"
            await session.flush()

            # 4. Run post-remediation reconciliation validation
            post_recon = await ReconciliationEngine.execute_reconciliation(
                session=session,
                tenant_id=tenant_id,
                account_number=proposal.account_number,
                server_name=proposal.server_name,
                reconstruction_run_id=new_recon_run.id,
                reconciliation_type="POST_REMEDIATION_VALIDATION",
            )
            proposal.new_reconciliation_run_id = post_recon.id

            # 5. Validation Check: Only promote if clean or data integrity score improved
            if post_recon.data_integrity_score >= Decimal("90.00") or post_recon.is_clean:
                # Atomically promote new run
                await ReconstructionManager.switch_active_run(
                    session=session,
                    tenant_id=tenant_id,
                    account_number=proposal.account_number,
                    target_run_id=new_recon_run.id,
                )

                proposal.status = "RESOLVED"
                proposal.resolved_at = datetime.now(timezone.utc)
                proposal.execution_result = {
                    "status": "SUCCESS",
                    "promoted_run_id": str(new_recon_run.id),
                    "post_reconciliation_run_id": str(post_recon.id),
                    "integrity_score": str(post_recon.data_integrity_score),
                    "grade": post_recon.integrity_grade,
                }

                # Update discrepancy status if attached
                if proposal.discrepancy_id:
                    stmt_d = select(ReconciliationDiscrepancy).where(
                        ReconciliationDiscrepancy.id == proposal.discrepancy_id
                    )
                    res_d = await session.execute(stmt_d)
                    disc = res_d.scalar_one_or_none()
                    if disc:
                        disc.status = "REMEDIATED"

            else:
                proposal.status = "FAILED"
                proposal.execution_result = {
                    "status": "VALIDATION_FAILED",
                    "reason": f"Integrity score {post_recon.data_integrity_score} below acceptance threshold",
                    "post_reconciliation_run_id": str(post_recon.id),
                }

            await session.flush()
            return proposal, post_recon

        except Exception as e:
            proposal.status = "FAILED"
            proposal.execution_result = {"status": "ERROR", "error": str(e)}
            await session.flush()
            raise
