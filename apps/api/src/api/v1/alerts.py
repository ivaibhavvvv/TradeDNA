"""
TradeDNA Operational Alerts API Endpoints
Provides authenticated, tenant-isolated alert listing, acknowledgment, and resolution.
"""

import uuid
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.dependencies import get_current_user
from src.core.exceptions import NotFoundException
from src.models.user import User
from src.services.alert_service import alert_service

router = APIRouter(prefix="/alerts", tags=["Operational Alerts"])


@router.get("", status_code=status.HTTP_200_OK)
async def list_alerts(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (OPEN, ACKNOWLEDGED, RESOLVED)"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> List[dict[str, Any]]:
    """Returns operational and financial integrity alerts for the authenticated tenant."""
    alerts = await alert_service.get_tenant_alerts(
        session=session,
        tenant_id=current_user.tenant_id,
        status=status_filter,
        limit=limit,
    )
    return [
        {
            "id": str(a.id),
            "alert_type": a.alert_type,
            "severity": a.severity,
            "status": a.status,
            "source": a.source,
            "message": a.message,
            "fingerprint": a.fingerprint,
            "correlation_id": a.correlation_id,
            "metadata": a.payload_metadata,
            "created_at": a.created_at.isoformat(),
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
            "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        }
        for a in alerts
    ]


@router.post("/{alert_id}/acknowledge", status_code=status.HTTP_200_OK)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Transitions an alert from OPEN to ACKNOWLEDGED."""
    alert = await alert_service.acknowledge_alert(
        session=session,
        tenant_id=current_user.tenant_id,
        alert_id=alert_id,
        user_id=current_user.id,
    )
    if not alert:
        raise NotFoundException("Operational alert not found or unauthorized.")
    return {
        "success": True,
        "alert_id": str(alert.id),
        "status": alert.status,
        "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
    }


@router.post("/{alert_id}/resolve", status_code=status.HTTP_200_OK)
async def resolve_alert(
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Transitions an alert to RESOLVED."""
    alert = await alert_service.resolve_alert(
        session=session,
        tenant_id=current_user.tenant_id,
        alert_id=alert_id,
        user_id=current_user.id,
    )
    if not alert:
        raise NotFoundException("Operational alert not found or unauthorized.")
    return {
        "success": True,
        "alert_id": str(alert.id),
        "status": alert.status,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
    }
