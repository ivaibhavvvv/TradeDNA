"""TradeDNA Phase 7 - Analytics & Behavioral Intelligence REST API Endpoints.
Provides authenticated, tenant-isolated access to performance analytics,
behavioral patterns, dimensional feature cubes, baselines, and Trading DNA profiles.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db_session
from src.core.dependencies import get_current_user
from src.models.analytics import (
    AnalyticsFeatureStore,
    AnalyticsSnapshot,
    BaselineComparison,
    BehavioralPattern,
    TradingDNAProfile,
)
from src.models.user import User
from src.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


# --- Pydantic Response Schemas ---

class AnalyticsOverviewResponse(BaseModel):
    account_number: int
    reconstruction_run_id: str
    reconciliation_run_id: Optional[str] = None
    data_integrity_score: Decimal
    integrity_grade: str
    is_compromised: bool
    data_trust_status: str
    quality_warnings: list[str] = []
    performance: dict[str, Any]
    trading_dna: dict[str, Any]
    detected_patterns_count: int
    calculation_version: str


class TriggerAnalyticsRequest(BaseModel):
    period_type: str = "ALL_TIME"
    server_name: Optional[str] = None
    start_time_utc: Optional[datetime] = None
    end_time_utc: Optional[datetime] = None
    target_reconstruction_run_id: Optional[uuid.UUID] = None
    target_reconciliation_run_id: Optional[uuid.UUID] = None


@router.post("/calculate/{account_number}", response_model=dict[str, Any])
async def trigger_analytics_calculation(
    account_number: int,
    req: TriggerAnalyticsRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Triggers calculation and persistence of Phase 7 analytics for the specified account.
    """
    try:
        res = await AnalyticsService.compute_and_persist_analytics(
            session=session,
            tenant_id=current_user.tenant_id,
            account_number=account_number,
            server_name=req.server_name,
            period_type=req.period_type,
            start_time_utc=req.start_time_utc,
            end_time_utc=req.end_time_utc,
            target_reconstruction_run_id=req.target_reconstruction_run_id,
            target_reconciliation_run_id=req.target_reconciliation_run_id,
        )
        await session.commit()
        return {
            "status": "COMPLETED",
            "snapshot_id": str(res["snapshot_id"]),
            "is_compromised": res["is_compromised"],
            "data_trust_status": res["data_trust_status"],
            "quality_warnings": res["quality_warnings"],
            "performance": res["performance"],
            "trading_dna": res["trading_dna"],
            "patterns_count": res["patterns_count"],
        }
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/overview/{account_number}", response_model=AnalyticsOverviewResponse)
async def get_analytics_overview(
    account_number: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Returns the latest consolidated analytics overview and Trading DNA profile.
    """
    # Fetch latest snapshot
    stmt_snap = (
        select(AnalyticsSnapshot)
        .where(
            AnalyticsSnapshot.tenant_id == current_user.tenant_id,
            AnalyticsSnapshot.account_number == account_number,
        )
        .order_by(AnalyticsSnapshot.created_at.desc())
    )
    res_snap = await session.execute(stmt_snap)
    snap = res_snap.scalar_one_or_none()

    if not snap:
        # Compute on demand if not yet cached
        res = await AnalyticsService.compute_and_persist_analytics(
            session=session,
            tenant_id=current_user.tenant_id,
            account_number=account_number,
        )
        await session.commit()
        return AnalyticsOverviewResponse(
            account_number=account_number,
            reconstruction_run_id=str(res["context"].reconstruction_run_id),
            reconciliation_run_id=str(res["context"].reconciliation_run_id) if res["context"].reconciliation_run_id else None,
            data_integrity_score=res["context"].data_integrity_score,
            integrity_grade=res["context"].integrity_grade,
            is_compromised=res["context"].is_compromised,
            data_trust_status=res["context"].data_trust_status,
            quality_warnings=list(res["context"].quality_warnings),
            performance=res["performance"],
            trading_dna=res["trading_dna"],
            detected_patterns_count=res["patterns_count"],
            calculation_version=res["context"].calculation_engine_version,
        )

    # Fetch latest DNA profile
    stmt_dna = (
        select(TradingDNAProfile)
        .where(
            TradingDNAProfile.tenant_id == current_user.tenant_id,
            TradingDNAProfile.account_number == account_number,
        )
        .order_by(TradingDNAProfile.synthesized_at.desc())
    )
    res_dna = await session.execute(stmt_dna)
    dna = res_dna.scalar_one_or_none()

    # Count patterns
    stmt_pat = (
        select(BehavioralPattern)
        .where(
            BehavioralPattern.tenant_id == current_user.tenant_id,
            BehavioralPattern.account_number == account_number,
            BehavioralPattern.reconstruction_run_id == snap.reconstruction_run_id,
        )
    )
    res_pat = await session.execute(stmt_pat)
    patterns = res_pat.scalars().all()

    dna_dict = {}
    if dna:
        dna_dict = {
            "primary_trading_style": dna.primary_trading_style,
            "risk_appetite_grade": dna.risk_appetite_grade,
            "consistency_score": float(dna.consistency_score),
            "discipline_score": float(dna.discipline_score),
            "radar_dimensions": dna.radar_dimensions,
            "top_strengths": dna.top_strengths,
            "top_weaknesses": dna.top_weaknesses,
        }

    return AnalyticsOverviewResponse(
        account_number=account_number,
        reconstruction_run_id=str(snap.reconstruction_run_id),
        reconciliation_run_id=str(snap.reconciliation_run_id) if snap.reconciliation_run_id else None,
        data_integrity_score=snap.data_integrity_score,
        integrity_grade=snap.integrity_grade,
        is_compromised=snap.is_compromised,
        data_trust_status="DATA_TRUST_DEGRADED" if snap.is_compromised else "TRUSTED",
        quality_warnings=[],
        performance=snap.metrics_json or {},
        trading_dna=dna_dict,
        detected_patterns_count=len(patterns),
        calculation_version=snap.calculation_version,
    )


@router.get("/performance/{account_number}")
async def get_performance_details(
    account_number: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Returns detailed performance metrics and trade statistics."""
    stmt = (
        select(AnalyticsSnapshot)
        .where(
            AnalyticsSnapshot.tenant_id == current_user.tenant_id,
            AnalyticsSnapshot.account_number == account_number,
        )
        .order_by(AnalyticsSnapshot.created_at.desc())
    )
    res = await session.execute(stmt)
    snap = res.scalar_one_or_none()
    if not snap:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No analytics snapshot found.")
    return snap.metrics_json


@router.get("/patterns/{account_number}")
async def get_behavioral_patterns(
    account_number: int,
    pattern_type: Optional[str] = None,
    min_severity: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Lists detected behavioral patterns with supporting trade evidence."""
    stmt = (
        select(BehavioralPattern)
        .where(
            BehavioralPattern.tenant_id == current_user.tenant_id,
            BehavioralPattern.account_number == account_number,
        )
        .order_by(BehavioralPattern.window_start_utc.desc())
    )
    if pattern_type:
        stmt = stmt.where(BehavioralPattern.pattern_type == pattern_type)
    if min_severity:
        stmt = stmt.where(BehavioralPattern.severity == min_severity)

    res = await session.execute(stmt)
    pats = res.scalars().all()

    return [
        {
            "id": str(p.id),
            "pattern_type": p.pattern_type,
            "severity": p.severity,
            "detection_status": p.detection_status,
            "evidence_strength": p.evidence_strength,
            "window_start_utc": p.window_start_utc.isoformat(),
            "window_end_utc": p.window_end_utc.isoformat(),
            "supporting_trade_ids": p.supporting_trade_ids,
            "evidence": p.evidence_payload,
            "affected_metrics": p.affected_metrics,
        }
        for p in pats
    ]


@router.get("/sessions/{account_number}")
async def get_session_analytics(
    account_number: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Returns dimensional performance cubes sliced by trading session."""
    stmt = select(AnalyticsFeatureStore).where(
        AnalyticsFeatureStore.tenant_id == current_user.tenant_id,
        AnalyticsFeatureStore.account_number == account_number,
        AnalyticsFeatureStore.dimension_type == "SESSION",
    )
    res = await session.execute(stmt)
    cubes = res.scalars().all()
    return [
        {
            "session_name": c.dimension_key,
            "trade_count": c.trade_count,
            "win_rate": str(c.win_rate),
            "net_pnl": str(c.net_pnl),
            "profit_factor": str(c.profit_factor),
            "volume_lots": str(c.volume_lots),
            "avg_holding_sec": c.avg_holding_sec,
        }
        for c in cubes
    ]


@router.get("/symbols/{account_number}")
async def get_symbol_analytics(
    account_number: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Returns dimensional performance cubes sliced by traded instrument."""
    stmt = select(AnalyticsFeatureStore).where(
        AnalyticsFeatureStore.tenant_id == current_user.tenant_id,
        AnalyticsFeatureStore.account_number == account_number,
        AnalyticsFeatureStore.dimension_type == "SYMBOL",
    )
    res = await session.execute(stmt)
    cubes = res.scalars().all()
    return [
        {
            "symbol": c.dimension_key,
            "trade_count": c.trade_count,
            "win_rate": str(c.win_rate),
            "net_pnl": str(c.net_pnl),
            "profit_factor": str(c.profit_factor),
            "volume_lots": str(c.volume_lots),
            "avg_holding_sec": c.avg_holding_sec,
        }
        for c in cubes
    ]


@router.get("/trading-dna/{account_number}")
async def get_trading_dna_profile(
    account_number: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Returns the synthesized Trading DNA profile."""
    stmt = (
        select(TradingDNAProfile)
        .where(
            TradingDNAProfile.tenant_id == current_user.tenant_id,
            TradingDNAProfile.account_number == account_number,
        )
        .order_by(TradingDNAProfile.synthesized_at.desc())
    )
    res = await session.execute(stmt)
    dna = res.scalar_one_or_none()
    if not dna:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Trading DNA profile found.")

    return {
        "primary_trading_style": dna.primary_trading_style,
        "risk_appetite_grade": dna.risk_appetite_grade,
        "consistency_score": str(dna.consistency_score),
        "discipline_score": str(dna.discipline_score),
        "execution_quality_score": str(dna.execution_quality_score),
        "favored_instruments": dna.favored_instruments,
        "favored_sessions": dna.favored_sessions,
        "radar_dimensions": dna.radar_dimensions,
        "top_strengths": dna.top_strengths,
        "top_weaknesses": dna.top_weaknesses,
        "behavioral_tendencies": dna.behavioral_tendencies,
        "synthesized_at": dna.synthesized_at.isoformat(),
        "calculation_version": dna.calculation_version,
    }


@router.get("/baselines/{account_number}")
async def get_baseline_comparisons(
    account_number: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Returns period comparison deltas and detected behavioral drifts."""
    stmt = (
        select(BaselineComparison)
        .where(
            BaselineComparison.tenant_id == current_user.tenant_id,
            BaselineComparison.account_number == account_number,
        )
        .order_by(BaselineComparison.created_at.desc())
    )
    res = await session.execute(stmt)
    comps = res.scalars().all()
    return [
        {
            "comparison_cohort": c.comparison_cohort,
            "overall_trajectory": c.overall_trajectory,
            "current_window": [c.current_start_utc.isoformat(), c.current_end_utc.isoformat()],
            "baseline_window": [c.baseline_start_utc.isoformat(), c.baseline_end_utc.isoformat()],
            "metric_comparisons": c.metric_comparisons,
            "detected_drifts": c.detected_drifts,
        }
        for c in comps
    ]
