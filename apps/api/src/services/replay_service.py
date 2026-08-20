from datetime import datetime
from typing import AsyncGenerator, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.raw_event import (
    RawAccountSnapshot,
    RawEventObservation,
    RawPositionSnapshot,
)


class ReplayService:
    """Provides 4 isolated, deterministic replay streams over Layer 1 raw observations.
    Never mutates raw records; guarantees 100% idempotent replay for Phase 5 ledger construction."""

    @staticmethod
    async def replay_deal_stream(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
        from_time_msc: Optional[int] = None,
        to_time_msc: Optional[int] = None,
        include_duplicates: bool = False,
    ) -> list[RawEventObservation]:
        """Deterministic deal replay stream sorted strictly by:
        (source_time_msc ASC, external_ticket ASC, observation_id ASC)."""
        stmt = (
            select(RawEventObservation)
            .where(
                RawEventObservation.tenant_id == tenant_id,
                RawEventObservation.account_number == account_number,
                RawEventObservation.event_type == "DEAL_EVENT",
            )
            .order_by(
                RawEventObservation.source_time_msc.asc(),
                RawEventObservation.external_ticket.asc(),
                RawEventObservation.observation_id.asc(),
            )
        )

        if from_time_msc is not None:
            stmt = stmt.where(RawEventObservation.source_time_msc >= from_time_msc)
        if to_time_msc is not None:
            stmt = stmt.where(RawEventObservation.source_time_msc <= to_time_msc)
        if not include_duplicates:
            stmt = stmt.where(RawEventObservation.observation_status != "DUPLICATE")

        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def replay_order_stream(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
        from_time_msc: Optional[int] = None,
        to_time_msc: Optional[int] = None,
        include_duplicates: bool = False,
    ) -> list[RawEventObservation]:
        """Deterministic order replay stream sorted strictly by:
        (source_time_msc ASC, external_ticket ASC, observation_id ASC)."""
        stmt = (
            select(RawEventObservation)
            .where(
                RawEventObservation.tenant_id == tenant_id,
                RawEventObservation.account_number == account_number,
                RawEventObservation.event_type == "ORDER_EVENT",
            )
            .order_by(
                RawEventObservation.source_time_msc.asc(),
                RawEventObservation.external_ticket.asc(),
                RawEventObservation.observation_id.asc(),
            )
        )

        if from_time_msc is not None:
            stmt = stmt.where(RawEventObservation.source_time_msc >= from_time_msc)
        if to_time_msc is not None:
            stmt = stmt.where(RawEventObservation.source_time_msc <= to_time_msc)
        if not include_duplicates:
            stmt = stmt.where(RawEventObservation.observation_status != "DUPLICATE")

        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def replay_account_snapshot_stream(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
        from_timestamp: Optional[datetime] = None,
        to_timestamp: Optional[datetime] = None,
    ) -> list[RawAccountSnapshot]:
        """Deterministic account snapshot replay stream sorted strictly by:
        (snapshot_time_utc ASC, received_at_utc ASC, id ASC)."""
        stmt = (
            select(RawAccountSnapshot)
            .where(
                RawAccountSnapshot.tenant_id == tenant_id,
                RawAccountSnapshot.account_number == account_number,
            )
            .order_by(
                RawAccountSnapshot.snapshot_time_utc.asc(),
                RawAccountSnapshot.received_at_utc.asc(),
                RawAccountSnapshot.id.asc(),
            )
        )

        if from_timestamp is not None:
            stmt = stmt.where(RawAccountSnapshot.snapshot_time_utc >= from_timestamp)
        if to_timestamp is not None:
            stmt = stmt.where(RawAccountSnapshot.snapshot_time_utc <= to_timestamp)

        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def replay_position_snapshot_stream(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
        from_timestamp: Optional[datetime] = None,
        to_timestamp: Optional[datetime] = None,
    ) -> list[RawPositionSnapshot]:
        """Deterministic position snapshot replay stream sorted strictly by:
        (snapshot_time_utc ASC, received_at_utc ASC, id ASC)."""
        stmt = (
            select(RawPositionSnapshot)
            .where(
                RawPositionSnapshot.tenant_id == tenant_id,
                RawPositionSnapshot.account_number == account_number,
            )
            .order_by(
                RawPositionSnapshot.snapshot_time_utc.asc(),
                RawPositionSnapshot.received_at_utc.asc(),
                RawPositionSnapshot.id.asc(),
            )
        )

        if from_timestamp is not None:
            stmt = stmt.where(RawPositionSnapshot.snapshot_time_utc >= from_timestamp)
        if to_timestamp is not None:
            stmt = stmt.where(RawPositionSnapshot.snapshot_time_utc <= to_timestamp)

        res = await session.execute(stmt)
        return list(res.scalars().all())
