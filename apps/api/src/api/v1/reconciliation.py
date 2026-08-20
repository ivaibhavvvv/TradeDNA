"""TradeDNA Phase 6 - Reconciliation and Remediation REST API Router
Provides authenticated endpoints for triggering reconciliations, inspecting discrepancies,
tracking integrity scores, and managing remediation lifecycles.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db_session
from src.core.dependencies import get_current_user
from src.models.reconciliation import (
    DataIntegrityScoreHistory,
    ReconciliationDiscrepancy,
    ReconciliationRun,
    RemediationProposal,
)
from src.models.sync_state import AccountSyncState
from src.models.user import User
from src.services.reconciliation_engine import ReconciliationEngine
from src.services.remediation_engine import (
    RemediationAuthorizationError,
    RemediationEngine,
)

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation & Data Integrity"])


class TriggerReconciliationRequest(BaseModel):
    account_number: int
    server_name: str
    reconstruction_run_id: Optional[uuid.UUID] = None
    snapshot_id: Optional[uuid.UUID] = None
    reconciliation_type: str = "POINT_IN_TIME_SNAPSHOT"
    as_of_time_msc: Optional[int] = None
    window_start_msc: Optional[int] = None
    window_end_msc: Optional[int] = None


class AcknowledgeDiscrepancyRequest(BaseModel):
    notes: str
    status: str = "ACKNOWLEDGED"  # ACKNOWLEDGED, EXPLAINED_BROKER_ANOMALY


class CreateProposalRequest(BaseModel):
    account_number: int
    server_name: str
    proposal_type: str  # TRIGGER_RECONSTRUCTION_REBUILD, BACKFILL_RAW_INGRESS, EXPLAIN_BROKER_ANOMALY
    discrepancy_id: Optional[uuid.UUID] = None
    proposed_action: dict[str, Any] = Field(default_factory=dict)


@router.post("/trigger", status_code=status.HTTP_201_CREATED)
async def trigger_reconciliation(
    req: TriggerReconciliationRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Triggers an on-demand reconciliation run."""
    # Identify reconstruction_run_id if not provided
    recon_run_id = req.reconstruction_run_id
    if not recon_run_id:
        stmt_sync = select(AccountSyncState).where(
            AccountSyncState.tenant_id == current_user.tenant_id,
            AccountSyncState.account_number == req.account_number,
            AccountSyncState.server_name == req.server_name,
        )
        res_sync = await db.execute(stmt_sync)
        sync_state = res_sync.scalar_one_or_none()
        if not sync_state or not sync_state.active_reconstruction_run_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active reconstruction run found for this account. Please specify reconstruction_run_id.",
            )
        recon_run_id = sync_state.active_reconstruction_run_id

    run = await ReconciliationEngine.execute_reconciliation(
        session=db,
        tenant_id=current_user.tenant_id,
        account_number=req.account_number,
        server_name=req.server_name,
        reconstruction_run_id=recon_run_id,
        snapshot_id=req.snapshot_id,
        reconciliation_type=req.reconciliation_type,
        as_of_time_msc=req.as_of_time_msc,
        window_start_msc=req.window_start_msc,
        window_end_msc=req.window_end_msc,
    )
    await db.commit()

    return {
        "reconciliation_run_id": str(run.id),
        "account_number": run.account_number,
        "status": run.status,
        "data_integrity_score": str(run.data_integrity_score),
        "integrity_grade": run.integrity_grade,
        "is_clean": run.is_clean,
        "discrepancy_count": run.discrepancy_count,
        "critical_count": run.critical_count,
        "high_count": run.high_count,
        "medium_count": run.medium_count,
        "low_count": run.low_count,
        "execution_time_ms": run.execution_time_ms,
    }


@router.get("/runs")
async def list_reconciliation_runs(
    account_number: Optional[int] = None,
    is_clean: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Lists reconciliation runs for tenant."""
    stmt = select(ReconciliationRun).where(ReconciliationRun.tenant_id == current_user.tenant_id)
    if account_number is not None:
        stmt = stmt.where(ReconciliationRun.account_number == account_number)
    if is_clean is not None:
        stmt = stmt.where(ReconciliationRun.is_clean == is_clean)
    stmt = stmt.order_by(ReconciliationRun.created_at.desc()).offset(offset).limit(limit)

    res = await db.execute(stmt)
    runs = res.scalars().all()

    return [
        {
            "id": str(r.id),
            "account_number": r.account_number,
            "server_name": r.server_name,
            "reconstruction_run_id": str(r.reconstruction_run_id),
            "status": r.status,
            "data_integrity_score": str(r.data_integrity_score),
            "integrity_grade": r.integrity_grade,
            "is_clean": r.is_clean,
            "discrepancy_count": r.discrepancy_count,
            "critical_count": r.critical_count,
            "high_count": r.high_count,
            "medium_count": r.medium_count,
            "low_count": r.low_count,
            "as_of_timestamp_utc": r.as_of_timestamp_utc.isoformat(),
            "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]


@router.get("/runs/{run_id}")
async def get_reconciliation_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Gets detailed summary for a reconciliation run."""
    stmt = select(ReconciliationRun).where(
        ReconciliationRun.tenant_id == current_user.tenant_id,
        ReconciliationRun.id == run_id,
    )
    res = await db.execute(stmt)
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reconciliation run not found")

    return {
        "id": str(run.id),
        "account_number": run.account_number,
        "server_name": run.server_name,
        "reconstruction_run_id": str(run.reconstruction_run_id),
        "snapshot_id": str(run.snapshot_id) if run.snapshot_id else None,
        "status": run.status,
        "data_integrity_score": str(run.data_integrity_score),
        "integrity_grade": run.integrity_grade,
        "is_clean": run.is_clean,
        "discrepancy_count": run.discrepancy_count,
        "critical_count": run.critical_count,
        "high_count": run.high_count,
        "medium_count": run.medium_count,
        "low_count": run.low_count,
        "info_count": run.info_count,
        "reconciliation_engine_version": run.reconciliation_engine_version,
        "tolerance_profile_version": run.tolerance_profile_version,
        "severity_policy_version": run.severity_policy_version,
        "execution_time_ms": run.execution_time_ms,
        "as_of_timestamp_utc": run.as_of_timestamp_utc.isoformat(),
        "created_at": run.created_at.isoformat(),
    }


@router.get("/runs/{run_id}/discrepancies")
async def list_run_discrepancies(
    run_id: uuid.UUID,
    severity: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Lists discrepancies for a reconciliation run."""
    stmt = select(ReconciliationDiscrepancy).where(
        ReconciliationDiscrepancy.tenant_id == current_user.tenant_id,
        ReconciliationDiscrepancy.reconciliation_run_id == run_id,
    )
    if severity:
        stmt = stmt.where(ReconciliationDiscrepancy.severity == severity.upper())
    stmt = stmt.order_by(ReconciliationDiscrepancy.detected_at.desc()).offset(offset).limit(limit)

    res = await db.execute(stmt)
    discs = res.scalars().all()

    return [
        {
            "id": str(d.id),
            "discrepancy_scope": d.discrepancy_scope,
            "discrepancy_category": d.discrepancy_category,
            "severity": d.severity,
            "entity_type": d.entity_type,
            "entity_identifier": d.entity_identifier,
            "broker_value": d.broker_value,
            "canonical_value": d.canonical_value,
            "delta_value": d.delta_value,
            "broker_source": d.broker_source,
            "canonical_source": d.canonical_source,
            "currency": d.currency,
            "tolerance_applied": d.tolerance_applied,
            "status": d.status,
            "detected_at": d.detected_at.isoformat(),
        }
        for d in discs
    ]


@router.get("/discrepancies/{discrepancy_id}")
async def get_discrepancy_detail(
    discrepancy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Gets detailed discrepancy context including full JSON payload."""
    stmt = select(ReconciliationDiscrepancy).where(
        ReconciliationDiscrepancy.tenant_id == current_user.tenant_id,
        ReconciliationDiscrepancy.id == discrepancy_id,
    )
    res = await db.execute(stmt)
    d = res.scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discrepancy not found")

    return {
        "id": str(d.id),
        "reconciliation_run_id": str(d.reconciliation_run_id),
        "account_number": d.account_number,
        "server_name": d.server_name,
        "discrepancy_scope": d.discrepancy_scope,
        "discrepancy_category": d.discrepancy_category,
        "severity": d.severity,
        "entity_type": d.entity_type,
        "entity_identifier": d.entity_identifier,
        "broker_value": d.broker_value,
        "canonical_value": d.canonical_value,
        "delta_value": d.delta_value,
        "broker_source": d.broker_source,
        "canonical_source": d.canonical_source,
        "currency": d.currency,
        "tolerance_applied": d.tolerance_applied,
        "status": d.status,
        "root_cause_category": d.root_cause_category,
        "remediation_proposal_id": str(d.remediation_proposal_id) if d.remediation_proposal_id else None,
        "details_json": d.details_json,
        "acknowledged_by": str(d.acknowledged_by) if d.acknowledged_by else None,
        "acknowledged_at": d.acknowledged_at.isoformat() if d.acknowledged_at else None,
        "acknowledgement_notes": d.acknowledgement_notes,
        "detected_at": d.detected_at.isoformat(),
    }


@router.post("/discrepancies/{discrepancy_id}/acknowledge")
async def acknowledge_discrepancy(
    discrepancy_id: uuid.UUID,
    req: AcknowledgeDiscrepancyRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Acknowledges or explains a discrepancy with audit notes."""
    stmt = select(ReconciliationDiscrepancy).where(
        ReconciliationDiscrepancy.tenant_id == current_user.tenant_id,
        ReconciliationDiscrepancy.id == discrepancy_id,
    )
    res = await db.execute(stmt)
    d = res.scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discrepancy not found")

    d.status = req.status
    d.acknowledged_by = current_user.id
    d.acknowledged_at = datetime.now(timezone.utc)
    d.acknowledgement_notes = req.notes
    await db.commit()

    return {"status": "SUCCESS", "discrepancy_id": str(d.id), "new_status": d.status}


@router.get("/accounts/{account_number}/integrity-score")
async def get_account_integrity_score_history(
    account_number: int,
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Gets integrity score history for account."""
    stmt = (
        select(DataIntegrityScoreHistory)
        .where(
            DataIntegrityScoreHistory.tenant_id == current_user.tenant_id,
            DataIntegrityScoreHistory.account_number == account_number,
        )
        .order_by(DataIntegrityScoreHistory.recorded_at.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    history = res.scalars().all()

    return [
        {
            "id": str(h.id),
            "reconciliation_run_id": str(h.reconciliation_run_id),
            "score": str(h.score),
            "grade": h.grade,
            "active_discrepancies": h.active_discrepancies,
            "critical_discrepancies": h.critical_discrepancies,
            "recorded_at": h.recorded_at.isoformat(),
        }
        for h in history
    ]


@router.post("/proposals", status_code=status.HTTP_201_CREATED)
async def create_remediation_proposal(
    req: CreateProposalRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Creates a remediation proposal."""
    proposal = await RemediationEngine.create_proposal(
        session=db,
        tenant_id=current_user.tenant_id,
        account_number=req.account_number,
        server_name=req.server_name,
        proposal_type=req.proposal_type,
        discrepancy_id=req.discrepancy_id,
        proposed_action=req.proposed_action,
    )
    await db.commit()
    return {
        "proposal_id": str(proposal.id),
        "status": proposal.status,
        "proposal_type": proposal.proposal_type,
    }


@router.post("/proposals/{proposal_id}/approve")
async def approve_remediation_proposal(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Approves a remediation proposal."""
    try:
        proposal = await RemediationEngine.approve_proposal(
            session=db,
            tenant_id=current_user.tenant_id,
            proposal_id=proposal_id,
            approved_by_user_id=current_user.id,
        )
        await db.commit()
        return {"status": "SUCCESS", "proposal_id": str(proposal.id), "new_status": proposal.status}
    except RemediationAuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/proposals/{proposal_id}/execute")
async def execute_remediation_proposal(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Executes a remediation proposal through non-destructive reconstruction & reconciliation."""
    try:
        proposal, post_recon = await RemediationEngine.execute_remediation(
            session=db,
            tenant_id=current_user.tenant_id,
            proposal_id=proposal_id,
        )
        await db.commit()
        return {
            "status": "SUCCESS",
            "proposal_id": str(proposal.id),
            "proposal_status": proposal.status,
            "execution_result": proposal.execution_result,
        }
    except RemediationAuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
