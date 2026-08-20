from datetime import datetime
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.connector_auth import verify_connector_hmac
from src.core.database import get_db_session
from src.core.dependencies import get_client_metadata, get_current_user
from src.core.exceptions import NotFoundException
from src.core.rate_limit import rate_limit
from src.models.device import Device
from src.models.sync_state import AccountSyncState
from src.models.user import User
from src.schemas.connector import (
    HandshakeExchangeRequest,
    HandshakeExchangeResponse,
    PairingTokenResponse,
    SyncRequestEnvelope,
    SyncResponse,
)
from src.services.connector_service import connector_service
from src.services.replay_service import ReplayService
from src.services.sync_engine import SyncEngine

router = APIRouter(prefix="/exness", tags=["Exness MT5 Connector"])


@router.post(
    "/connection/pair",
    response_model=PairingTokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, tier="PAIRING"))],
    summary="Initiate Connector Pairing Handshake",
)
async def create_pairing_token(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    ip, ua = get_client_metadata(request)
    return await connector_service.create_pairing_token(
        db=db,
        current_user=current_user,
        ip_address=ip,
        user_agent=ua,
    )


@router.post(
    "/connection/exchange",
    response_model=HandshakeExchangeResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, tier="PAIRING"))],
    summary="Exchange Pairing Token for Device Credentials",
)
async def exchange_pairing_token(
    req: HandshakeExchangeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    ip, ua = get_client_metadata(request)
    return await connector_service.exchange_pairing_token(
        db=db,
        req=req,
        ip_address=ip,
        user_agent=ua,
    )


@router.post(
    "/connection/revoke/{device_id}",
    status_code=status.HTTP_200_OK,
    summary="Revoke Connector Device",
)
async def revoke_device(
    device_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    ip, ua = get_client_metadata(request)
    return await connector_service.revoke_device(
        db=db,
        device_id=device_id,
        current_user=current_user,
        ip_address=ip,
        user_agent=ua,
    )


@router.get(
    "/devices",
    status_code=status.HTTP_200_OK,
    summary="List Registered Connector Devices",
)
async def list_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(Device).where(Device.tenant_id == current_user.tenant_id)
    res = await db.execute(stmt)
    devices = res.scalars().all()
    return [
        {
            "id": str(d.id),
            "broker": d.broker,
            "account_number": d.account_number,
            "server_name": d.server_name,
            "trade_mode": d.trade_mode,
            "currency": d.currency,
            "terminal_build": d.terminal_build,
            "connector_version": d.connector_version,
            "is_active": d.is_active,
            "is_revoked": d.is_revoked,
            "last_seen_at": d.last_seen_at.isoformat(),
            "last_sync_time_msc": d.last_sync_time_msc,
            "last_sync_deal_ticket": d.last_sync_deal_ticket,
        }
        for d in devices
    ]


@router.post(
    "/sync",
    response_model=SyncResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(max_requests=300, window_seconds=60, tier="INGRESS"))],
    summary="Ingest Authenticated Connector Data Envelope",
)
async def sync_data(
    envelope: SyncRequestEnvelope,
    request: Request,
    device: Device = Depends(verify_connector_hmac),
    db: AsyncSession = Depends(get_db_session),
):
    raw_bytes = await request.body()
    return await connector_service.process_sync_payload(
        db=db,
        device=device,
        envelope=envelope,
        raw_body_bytes=raw_bytes,
    )


@router.get(
    "/sync-state/{account_number}",
    status_code=status.HTTP_200_OK,
    summary="Get Logical Account Synchronization State",
)
async def get_sync_state(
    account_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    sync_state = await SyncEngine.evaluate_sync_state(
        session=db,
        tenant_id=current_user.tenant_id,
        account_number=account_number,
    )
    if not sync_state:
        raise NotFoundException("Account synchronization state not found.")

    return {
        "id": str(sync_state.id),
        "broker": sync_state.broker,
        "account_number": sync_state.account_number,
        "server_name": sync_state.server_name,
        "currency": sync_state.currency,
        "trade_mode": sync_state.trade_mode,
        "sync_status": sync_state.sync_status,
        "current_cursor_time_msc": sync_state.current_cursor_time_msc,
        "current_cursor_deal_ticket": sync_state.current_cursor_deal_ticket,
        "last_successful_sync_at": sync_state.last_successful_sync_at.isoformat() if sync_state.last_successful_sync_at else None,
        "detected_anomalies_count": sync_state.detected_anomalies_count,
    }


@router.get(
    "/replay/deals/{account_number}",
    status_code=status.HTTP_200_OK,
    summary="Deterministic Deal Replay Stream",
)
async def replay_deals(
    account_number: int,
    from_msc: Optional[int] = Query(None),
    to_msc: Optional[int] = Query(None),
    include_duplicates: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    deals = await ReplayService.replay_deal_stream(
        session=db,
        tenant_id=current_user.tenant_id,
        account_number=account_number,
        from_time_msc=from_msc,
        to_time_msc=to_msc,
        include_duplicates=include_duplicates,
    )
    return [
        {
            "observation_id": str(d.observation_id),
            "external_ticket": d.external_ticket,
            "source_time_msc": d.source_time_msc,
            "item_payload_hash": d.item_payload_hash,
            "observation_status": d.observation_status,
            "data": d.raw_item_json,
        }
        for d in deals
    ]


@router.get(
    "/replay/orders/{account_number}",
    status_code=status.HTTP_200_OK,
    summary="Deterministic Order Replay Stream",
)
async def replay_orders(
    account_number: int,
    from_msc: Optional[int] = Query(None),
    to_msc: Optional[int] = Query(None),
    include_duplicates: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    orders = await ReplayService.replay_order_stream(
        session=db,
        tenant_id=current_user.tenant_id,
        account_number=account_number,
        from_time_msc=from_msc,
        to_time_msc=to_msc,
        include_duplicates=include_duplicates,
    )
    return [
        {
            "observation_id": str(o.observation_id),
            "external_ticket": o.external_ticket,
            "source_time_msc": o.source_time_msc,
            "item_payload_hash": o.item_payload_hash,
            "observation_status": o.observation_status,
            "data": o.raw_item_json,
        }
        for o in orders
    ]


@router.get(
    "/replay/snapshots/{account_number}",
    status_code=status.HTTP_200_OK,
    summary="Deterministic Account Snapshot Replay Stream",
)
async def replay_snapshots(
    account_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    snapshots = await ReplayService.replay_account_snapshot_stream(
        session=db,
        tenant_id=current_user.tenant_id,
        account_number=account_number,
    )
    return [
        {
            "id": str(s.id),
            "currency": s.currency,
            "balance": str(s.balance),
            "equity": str(s.equity),
            "margin": str(s.margin),
            "margin_free": str(s.margin_free),
            "margin_level": str(s.margin_level),
            "snapshot_time_utc": s.snapshot_time_utc.isoformat(),
        }
        for s in snapshots
    ]
