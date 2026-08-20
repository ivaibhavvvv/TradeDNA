from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.sync_state import AccountSyncState, SyncGapEvent


class SyncEngine:
    """Manages logical Account Synchronization state machine transitions,
    timeout checks, and anomaly gap classification."""

    INACTIVITY_TIMEOUT_SECONDS = 120

    @classmethod
    async def evaluate_sync_state(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
    ) -> Optional[AccountSyncState]:
        """Evaluates active synchronization state and transitions to STALE
        if connector has been silent for > 120 seconds."""
        stmt = select(AccountSyncState).where(
            AccountSyncState.tenant_id == tenant_id,
            AccountSyncState.account_number == account_number,
        )
        res = await session.execute(stmt)
        sync_state = res.scalar_one_or_none()

        if not sync_state:
            return None

        now = datetime.now(timezone.utc)
        if sync_state.last_successful_sync_at:
            last_sync = sync_state.last_successful_sync_at
            if last_sync.tzinfo is None:
                last_sync = last_sync.replace(tzinfo=timezone.utc)
            elapsed = (now - last_sync).total_seconds()
            if elapsed > cls.INACTIVITY_TIMEOUT_SECONDS and sync_state.sync_status == "CURRENT":
                sync_state.sync_status = "STALE"
                await session.flush()

        return sync_state

    @classmethod
    async def record_gap_event(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_sync_id: uuid.UUID,
        account_number: int,
        classification: str,
        category: str,
        evidence: dict,
    ) -> SyncGapEvent:
        """Records synchronization anomaly or gap to the audit registry."""
        gap_event = SyncGapEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            account_sync_id=account_sync_id,
            account_number=account_number,
            gap_classification=classification,
            anomaly_category=category,
            evidence_details=evidence,
        )
        session.add(gap_event)

        if classification == "CONFIRMED_GAP":
            sync_state_stmt = select(AccountSyncState).where(AccountSyncState.id == account_sync_id)
            s_res = await session.execute(sync_state_stmt)
            s = s_res.scalar_one_or_none()
            if s:
                s.detected_anomalies_count += 1
                s.sync_status = "GAP_DETECTED"

        await session.flush()
        return gap_event
