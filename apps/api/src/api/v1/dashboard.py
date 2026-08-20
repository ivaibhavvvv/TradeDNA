"""TradeDNA Phase 8 - Dashboard BFF (Backend-For-Frontend) REST API Router.
Delivers consolidated, authenticated dashboard view models to Next.js frontend,
enforcing server-side account ownership and tenant isolation.
"""

from typing import Any, Optional
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db_session
from src.core.dependencies import get_current_user
from src.core.rate_limit import rate_limit
from src.models.user import User
from src.services.dashboard_service import DashboardService

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard BFF"],
    dependencies=[Depends(rate_limit(max_requests=120, window_seconds=60, tier="DASHBOARD"))],
)


class SyncTriggerRequest(BaseModel):
    account_number: int = Field(..., description="Authorized Exness account number to trigger sync for")


@router.get("/overview", status_code=status.HTTP_200_OK)
async def get_dashboard_overview(
    account_number: Optional[int] = Query(None, description="Optional account number; defaults to tenant primary account"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Returns consolidated dashboard overview for authenticated tenant/user."""
    return await DashboardService.get_dashboard_overview(
        session=session,
        user=current_user,
        account_number=account_number,
    )


@router.get("/accounts", status_code=status.HTTP_200_OK)
async def get_authorized_accounts(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    """Returns list of authorized Exness accounts for the authenticated user's tenant."""
    return await DashboardService.get_authorized_accounts(
        session=session,
        user=current_user,
    )


@router.post("/sync-trigger", status_code=status.HTTP_200_OK)
async def trigger_dashboard_sync(
    payload: SyncTriggerRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Records a backend synchronization request for the specified authorized account."""
    return await DashboardService.request_sync_trigger(
        session=session,
        user=current_user,
        account_number=payload.account_number,
    )


@router.get("/sync-telemetry", status_code=status.HTTP_200_OK)
async def get_dashboard_sync_telemetry(
    account_number: Optional[int] = Query(None, description="Optional account number; defaults to primary account"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Returns authoritative real-time data freshness, reachability, and sync telemetry."""
    return await DashboardService.get_sync_telemetry(
        session=session,
        user=current_user,
        account_number=account_number,
    )



@router.get("/performance", status_code=status.HTTP_200_OK)
async def get_performance_analytics(
    account_number: Optional[int] = Query(None, description="Optional account number"),
    period: str = Query("ALL", description="Time period filter (7D, 30D, 90D, 6M, 1Y, ALL)"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Returns performance analytics, equity progression time series, and daily P&L bars."""
    return await DashboardService.get_performance_analytics(
        session=session,
        user=current_user,
        account_number=account_number,
        period=period,
    )


@router.get("/trades", status_code=status.HTTP_200_OK)
async def get_canonical_trades(
    account_number: Optional[int] = Query(None, description="Optional account number"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    symbol: Optional[str] = Query(None, description="Filter by symbol (e.g. XAUUSD)"),
    direction: Optional[str] = Query(None, description="Filter by direction (BUY, SELL)"),
    result: Optional[str] = Query(None, description="Filter by result (ALL, WIN, LOSS)"),
    search: Optional[str] = Query(None, description="Search term in symbol"),
    sort_by: str = Query("opened_at_utc", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc, desc)"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Returns paginated, filterable canonical trades for the authenticated tenant."""
    return await DashboardService.get_canonical_trades(
        session=session,
        user=current_user,
        account_number=account_number,
        limit=limit,
        offset=offset,
        symbol=symbol,
        direction=direction,
        result=result,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/trades/{trade_id}", status_code=status.HTTP_200_OK)
async def get_trade_detail(
    trade_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Returns canonical trade lifecycle, executions, and behavioral citations."""
    return await DashboardService.get_trade_detail(
        session=session,
        user=current_user,
        trade_id=trade_id,
    )


@router.get("/risk", status_code=status.HTTP_200_OK)
async def get_risk_analytics(
    account_number: Optional[int] = Query(None, description="Optional account number"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Returns risk, leverage, drawdown velocity, and symbol concentration metrics."""
    return await DashboardService.get_risk_analytics(
        session=session,
        user=current_user,
        account_number=account_number,
    )


@router.get("/behavior", status_code=status.HTTP_200_OK)
async def get_behavioral_intelligence(
    account_number: Optional[int] = Query(None, description="Optional account number"),
    pattern_type: Optional[str] = Query(None, description="Filter by pattern type"),
    severity: Optional[str] = Query(None, description="Filter by severity (INFO, LOW, MEDIUM, HIGH, CRITICAL)"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Returns behavioral anomaly pattern feed with chronological timeline and citations."""
    return await DashboardService.get_behavioral_intelligence(
        session=session,
        user=current_user,
        account_number=account_number,
        pattern_type=pattern_type,
        severity=severity,
    )


@router.get("/trading-dna", status_code=status.HTTP_200_OK)
async def get_trading_dna(
    account_number: Optional[int] = Query(None, description="Optional account number"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Returns 5-axis Spider Radar synthesis, primary style, and behavioral tendencies."""
    return await DashboardService.get_trading_dna(
        session=session,
        user=current_user,
        account_number=account_number,
    )


@router.get("/instruments", status_code=status.HTTP_200_OK)
async def get_instruments_analytics(
    account_number: Optional[int] = Query(None, description="Optional account number"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Returns per-symbol performance, win rates, and volume distribution."""
    return await DashboardService.get_instruments_analytics(
        session=session,
        user=current_user,
        account_number=account_number,
    )


@router.get("/sessions", status_code=status.HTTP_200_OK)
async def get_sessions_analytics(
    account_number: Optional[int] = Query(None, description="Optional account number"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Returns market session breakdowns (Asian, London, London/NY, NY) and 24h heatmap."""
    return await DashboardService.get_sessions_analytics(
        session=session,
        user=current_user,
        account_number=account_number,
    )


@router.get("/calendar", status_code=status.HTTP_200_OK)
async def get_calendar_analytics(
    account_number: Optional[int] = Query(None, description="Optional account number"),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Returns daily realized P&L calendar matrix and trade frequency."""
    return await DashboardService.get_calendar_analytics(
        session=session,
        user=current_user,
        account_number=account_number,
        year=year,
        month=month,
    )


@router.get("/operations", status_code=status.HTTP_200_OK)
async def get_operations_overview(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Returns operational intelligence, system health, connector telemetry, and live alerts."""
    return await DashboardService.get_operations_overview(
        session=session,
        user=current_user,
    )


@router.get("/recovery", status_code=status.HTTP_200_OK)
async def get_recovery_overview(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Returns disaster recovery, backup manifests, financial integrity verification, and RPO/RTO metrics."""
    return await DashboardService.get_recovery_overview(
        session=session,
        user=current_user,
    )


