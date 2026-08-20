from typing import Any, Dict
import uuid
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db_session
from src.core.dependencies import get_client_metadata, get_current_user
from src.core.rate_limit import rate_limit
from src.models.user import User
from src.schemas.connection import (
    AccountRevocationResponse,
    ConnectionAccountDTO,
    ConnectionsOverviewResponse,
    DeviceRevocationResponse,
    UpdateAccountDisplayNameRequest,
)
from src.schemas.connector import PairingTokenResponse
from src.services.connection_service import connection_service
from src.services.connector_service import connector_service

router = APIRouter(prefix="/connections", tags=["Exness Connection Center"])


@router.get(
    "",
    response_model=ConnectionsOverviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Connection Center Overview",
    dependencies=[Depends(rate_limit(max_requests=120, window_seconds=60, tier="DASHBOARD"))],
)
async def get_connections_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ConnectionsOverviewResponse:
    """Returns aggregated connection and device telemetry for all authorized accounts."""
    return await connection_service.get_overview(db=db, user=current_user)


@router.get(
    "/{account_number}",
    response_model=ConnectionAccountDTO,
    status_code=status.HTTP_200_OK,
    summary="Get Detailed Connection Telemetry for Account",
    dependencies=[Depends(rate_limit(max_requests=120, window_seconds=60, tier="DASHBOARD"))],
)
async def get_account_connection_detail(
    account_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ConnectionAccountDTO:
    """Returns detailed connection timeline and device list for a single account."""
    return await connection_service.get_account_detail(db=db, user=current_user, account_number=account_number)


@router.post(
    "/pair",
    response_model=PairingTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate New MT5 Connector Pairing",
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, tier="PAIRING"))],
)
async def create_pairing_token(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> PairingTokenResponse:
    """Generates an ephemeral 15-minute single-use pairing token."""
    ip, ua = get_client_metadata(request)
    return await connector_service.create_pairing_token(
        db=db,
        current_user=current_user,
        ip_address=ip,
        user_agent=ua,
    )


@router.post(
    "/devices/{device_id}/revoke",
    response_model=DeviceRevocationResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke Connector Device",
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, tier="PAIRING"))],
)
async def revoke_device(
    device_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> DeviceRevocationResponse:
    """Revokes a specific MT5 terminal device, halting all ingress immediately."""
    ip, ua = get_client_metadata(request)
    return await connection_service.revoke_device(
        db=db,
        user=current_user,
        device_id=device_id,
        ip_address=ip,
        user_agent=ua,
    )


@router.post(
    "/accounts/{account_number}/revoke-all",
    response_model=AccountRevocationResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke All Devices for Account",
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, tier="PAIRING"))],
)
async def revoke_all_devices(
    account_number: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> AccountRevocationResponse:
    """Revokes all active MT5 connector devices bound to an account."""
    ip, ua = get_client_metadata(request)
    return await connection_service.revoke_all_devices(
        db=db,
        user=current_user,
        account_number=account_number,
        ip_address=ip,
        user_agent=ua,
    )


@router.patch(
    "/accounts/{account_number}/display-name",
    response_model=ConnectionAccountDTO,
    status_code=status.HTTP_200_OK,
    summary="Update Local Account Display Label",
    dependencies=[Depends(rate_limit(max_requests=30, window_seconds=60, tier="DASHBOARD"))],
)
async def update_display_name(
    account_number: int,
    payload: UpdateAccountDisplayNameRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ConnectionAccountDTO:
    """Updates local display label for an authorized account."""
    return await connection_service.update_display_name(
        db=db,
        user=current_user,
        account_number=account_number,
        display_name=payload.display_name,
    )


@router.delete(
    "/accounts/{account_number}",
    status_code=status.HTTP_200_OK,
    summary="Remove Account View or Purge All Data",
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, tier="DASHBOARD"))],
)
async def remove_account(
    account_number: int,
    request: Request,
    purge: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Removes an account view or permanently purges all associated account data."""
    if purge:
        ip, ua = get_client_metadata(request)
        return await connection_service.purge_account(
            db=db,
            user=current_user,
            account_number=account_number,
            ip_address=ip,
            user_agent=ua,
        )
    return await connection_service.soft_delete_account(
        db=db,
        user=current_user,
        account_number=account_number,
    )


@router.delete(
    "/accounts/{account_number}/purge",
    status_code=status.HTTP_200_OK,
    summary="Permanently Purge Account and All Associated Data",
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, tier="DASHBOARD"))],
)
async def purge_account_data(
    account_number: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Permanently deletes account, devices, trades, snapshots, and analytics for authenticated tenant."""
    ip, ua = get_client_metadata(request)
    return await connection_service.purge_account(
        db=db,
        user=current_user,
        account_number=account_number,
        ip_address=ip,
        user_agent=ua,
    )
