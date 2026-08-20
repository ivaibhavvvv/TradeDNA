"""
TradeDNA Operational & Financial Integrity Alert Service
Provides deterministic alert fingerprinting, deduplication, tenant isolation,
and full lifecycle management (OPEN -> ACKNOWLEDGED -> RESOLVED).
"""

import time
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.alert import OperationalAlert
from src.core.logging import logger


def generate_alert_fingerprint(
    tenant_id: uuid.UUID,
    alert_type: str,
    relevant_entity: str,
    time_window_seconds: int = 900,  # 15-minute deduplication bucket
) -> str:
    """Generates a deterministic SHA-256 fingerprint for alert deduplication."""
    time_bucket = int(time.time() // time_window_seconds)
    raw_key = f"{tenant_id}_{alert_type}_{relevant_entity}_{time_bucket}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class AlertService:
    """Service managing operational alerts and financial integrity alarms."""

    @staticmethod
    async def create_alert(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        alert_type: str,
        severity: str,
        message: str,
        source: str = "SYSTEM",
        relevant_entity: str = "default",
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OperationalAlert:
        """
        Creates an operational alert with deterministic deduplication.
        If an identical alert is currently OPEN or ACKNOWLEDGED in the active time window,
        returns the existing alert without creating a duplicate.
        """
        fingerprint = generate_alert_fingerprint(tenant_id, alert_type, relevant_entity)

        # Check for existing active alert with same fingerprint
        stmt = (
            select(OperationalAlert)
            .where(
                and_(
                    OperationalAlert.tenant_id == tenant_id,
                    OperationalAlert.fingerprint == fingerprint,
                    OperationalAlert.status.in_(["OPEN", "ACKNOWLEDGED"]),
                )
            )
            .order_by(OperationalAlert.created_at.desc())
        )
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            logger.info(f"Deduplicated alert [type={alert_type}, fingerprint={fingerprint[:8]}]. Returning active alert {existing.id}.")
            return existing

        new_alert = OperationalAlert(
            tenant_id=tenant_id,
            alert_type=alert_type,
            severity=severity.upper(),
            status="OPEN",
            source=source.upper(),
            message=message,
            correlation_id=correlation_id,
            fingerprint=fingerprint,
            payload_metadata=metadata or {},
            created_at=datetime.now(timezone.utc),
        )
        session.add(new_alert)
        await session.flush()
        logger.warning(f"Created operational alert {new_alert.id} [type={alert_type}, severity={severity}]: {message}")
        return new_alert

    @staticmethod
    async def acknowledge_alert(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        alert_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[OperationalAlert]:
        """Transitions an alert from OPEN to ACKNOWLEDGED."""
        stmt = (
            select(OperationalAlert)
            .where(
                and_(
                    OperationalAlert.id == alert_id,
                    OperationalAlert.tenant_id == tenant_id,
                )
            )
        )
        res = await session.execute(stmt)
        alert = res.scalar_one_or_none()
        if not alert:
            return None

        alert.status = "ACKNOWLEDGED"
        alert.acknowledged_at = datetime.now(timezone.utc)
        alert.acknowledged_by = user_id
        await session.flush()
        logger.info(f"Alert {alert_id} acknowledged by user {user_id}.")
        return alert

    @staticmethod
    async def resolve_alert(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        alert_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[OperationalAlert]:
        """Transitions an alert to RESOLVED."""
        stmt = (
            select(OperationalAlert)
            .where(
                and_(
                    OperationalAlert.id == alert_id,
                    OperationalAlert.tenant_id == tenant_id,
                )
            )
        )
        res = await session.execute(stmt)
        alert = res.scalar_one_or_none()
        if not alert:
            return None

        alert.status = "RESOLVED"
        alert.resolved_at = datetime.now(timezone.utc)
        alert.resolved_by = user_id
        await session.flush()
        logger.info(f"Alert {alert_id} resolved by user {user_id}.")
        return alert

    @staticmethod
    async def get_tenant_alerts(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[OperationalAlert]:
        """Fetches operational alerts for a tenant with strict isolation."""
        query = select(OperationalAlert).where(OperationalAlert.tenant_id == tenant_id)
        if status:
            query = query.where(OperationalAlert.status == status.upper())
        query = query.order_by(OperationalAlert.created_at.desc()).limit(limit)

        res = await session.execute(query)
        return list(res.scalars().all())


alert_service = AlertService()
