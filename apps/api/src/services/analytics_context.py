"""TradeDNA Phase 7 - Analytics Calculation Context & Data Integrity Gate.
Enforces that all downstream analytical engines operate on a single, authoritative,
and validated context tied to Phase 5 Canonical Truth and Phase 6 Reconciliation State.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.reconciliation import ReconciliationRun
from src.models.reconstruction_run import ReconstructionRun
from src.models.sync_state import AccountSyncState

ANALYTICS_ENGINE_VERSION = "7.0.0"
ANALYTICS_CONFIG_VERSION = "1.0.0"
INTEGRITY_SCORE_TRUST_THRESHOLD = Decimal("90.00")
ACCEPTABLE_INTEGRITY_GRADES = {"AAA", "AA", "A"}


@dataclass(frozen=True)
class AnalyticsCalculationContext:
    """
    Authoritative calculation context passed to all Phase 7 analytics engines.
    Guarantees consistent tenant, account, reconstruction run, reconciliation run,
    currency, and versioning across all analytical operations.
    """
    tenant_id: uuid.UUID
    broker: str
    account_number: int
    server_name: str
    reconstruction_run_id: uuid.UUID
    reconciliation_run_id: Optional[uuid.UUID]
    data_integrity_score: Decimal
    integrity_grade: str
    is_compromised: bool
    data_trust_status: str  # TRUSTED, DATA_TRUST_DEGRADED
    quality_warnings: tuple[str, ...]
    reporting_currency: str
    calculation_engine_version: str = ANALYTICS_ENGINE_VERSION
    configuration_version: str = ANALYTICS_CONFIG_VERSION
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None


class AnalyticsContextResolver:
    """
    Resolves and validates the AnalyticsCalculationContext from database state.
    Implements the Data Integrity Gate to prevent silent calculation from compromised data.
    """

    @classmethod
    async def resolve_context(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
        server_name: Optional[str] = None,
        broker: str = "EXNESS",
        target_reconstruction_run_id: Optional[uuid.UUID] = None,
        target_reconciliation_run_id: Optional[uuid.UUID] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> AnalyticsCalculationContext:
        """
        Resolves the authoritative calculation context, checking active sync state,
        reconstruction run validity, and reconciliation integrity scores.
        """
        # 1. Resolve Account Sync State
        stmt_sync = select(AccountSyncState).where(
            AccountSyncState.tenant_id == tenant_id,
            AccountSyncState.account_number == account_number,
        )
        if server_name:
            stmt_sync = stmt_sync.where(AccountSyncState.server_name == server_name)
        res_sync = await session.execute(stmt_sync)
        sync_state = res_sync.scalar_one_or_none()

        actual_server = server_name or (sync_state.server_name if sync_state else "Exness-Real")
        reporting_currency = sync_state.currency if sync_state else "USD"

        # 2. Resolve Reconstruction Run
        recon_run_id = target_reconstruction_run_id
        if not recon_run_id and sync_state and sync_state.active_reconstruction_run_id:
            recon_run_id = sync_state.active_reconstruction_run_id

        if not recon_run_id:
            # Fallback to latest completed reconstruction run for this tenant & account
            stmt_run = (
                select(ReconstructionRun)
                .where(
                    ReconstructionRun.tenant_id == tenant_id,
                    ReconstructionRun.account_number == account_number,
                    ReconstructionRun.status.in_(["ACTIVE", "COMPLETED", "SUPERSEDED"]),
                )
                .order_by(ReconstructionRun.created_at.desc())
            )
            res_run = await session.execute(stmt_run)
            latest_run = res_run.scalar_one_or_none()
            if latest_run:
                recon_run_id = latest_run.id
            else:
                raise ValueError(
                    f"No ReconstructionRun found for tenant {tenant_id} and account {account_number}. "
                    "Phase 5 canonical reconstruction must be executed before Phase 7 analytics."
                )

        # 3. Resolve Reconciliation Run & Assess Integrity Gate
        warnings: list[str] = []
        is_compromised = False
        data_trust_status = "TRUSTED"
        integrity_score = Decimal("100.00")
        integrity_grade = "AAA"
        resolved_recon_run_id = target_reconciliation_run_id

        if resolved_recon_run_id:
            stmt_recon = select(ReconciliationRun).where(
                ReconciliationRun.id == resolved_recon_run_id,
                ReconciliationRun.tenant_id == tenant_id,
            )
            res_recon = await session.execute(stmt_recon)
            recon_run = res_recon.scalar_one_or_none()
        else:
            # Look for latest completed reconciliation run for this reconstruction run
            stmt_recon = (
                select(ReconciliationRun)
                .where(
                    ReconciliationRun.tenant_id == tenant_id,
                    ReconciliationRun.account_number == account_number,
                    ReconciliationRun.reconstruction_run_id == recon_run_id,
                    ReconciliationRun.status == "COMPLETED",
                )
                .order_by(ReconciliationRun.created_at.desc())
            )
            res_recon = await session.execute(stmt_recon)
            recon_run = res_recon.scalar_one_or_none()

        if recon_run:
            resolved_recon_run_id = recon_run.id
            integrity_score = recon_run.data_integrity_score
            integrity_grade = recon_run.integrity_grade

            if integrity_score < INTEGRITY_SCORE_TRUST_THRESHOLD or integrity_grade not in ACCEPTABLE_INTEGRITY_GRADES:
                is_compromised = True
                data_trust_status = "DATA_TRUST_DEGRADED"
                warnings.append(
                    f"Data integrity score {integrity_score} ({integrity_grade}) is below trust threshold "
                    f"{INTEGRITY_SCORE_TRUST_THRESHOLD}. Analytical outputs may reflect broker/ledger discrepancies."
                )
            if recon_run.critical_count > 0 or recon_run.high_count > 0:
                is_compromised = True
                data_trust_status = "DATA_TRUST_DEGRADED"
                warnings.append(
                    f"Reconciliation detected {recon_run.critical_count} critical and {recon_run.high_count} high "
                    "discrepancies between MT5 broker truth and canonical double-entry ledger."
                )
        else:
            # Reconciliation has not been run for this reconstruction
            warnings.append(
                "No completed Phase 6 ReconciliationRun found for this canonical dataset. "
                "Analytics computed without point-in-time broker validation."
            )

        return AnalyticsCalculationContext(
            tenant_id=tenant_id,
            broker=broker,
            account_number=account_number,
            server_name=actual_server,
            reconstruction_run_id=recon_run_id,
            reconciliation_run_id=resolved_recon_run_id,
            data_integrity_score=integrity_score,
            integrity_grade=integrity_grade,
            is_compromised=is_compromised,
            data_trust_status=data_trust_status,
            quality_warnings=tuple(warnings),
            reporting_currency=reporting_currency,
            calculation_engine_version=ANALYTICS_ENGINE_VERSION,
            configuration_version=ANALYTICS_CONFIG_VERSION,
            period_start=period_start,
            period_end=period_end,
        )
