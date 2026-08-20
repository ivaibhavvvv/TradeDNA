from typing import Annotated
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db_session
from src.core.dependencies import get_client_metadata, get_current_user
from src.core.rate_limit import rate_limit
from src.models.user import User
from src.schemas.onboarding import (
    CompleteOnboardingResponse,
    OnboardingStateResponse,
    PairInitiateRequest,
    PairInitiateResponse,
    ResendCodeResponse,
    SyncStatusResponse,
    VerifyEmailRequest,
    WorkspaceConfigRequest,
)
from src.services.onboarding_service import onboarding_service

router = APIRouter(prefix="/onboarding", tags=["SaaS Onboarding Experience"])


@router.get(
    "/state",
    response_model=OnboardingStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Current Onboarding State",
    dependencies=[Depends(rate_limit(max_requests=60, window_seconds=60, tier="AUTH"))],
)
async def get_onboarding_state(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> OnboardingStateResponse:
    """Returns the authenticated user's persistent onboarding progress."""
    return await onboarding_service.get_state(db=db, user=current_user)


@router.post(
    "/verify-email",
    response_model=OnboardingStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify Email Code",
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, tier="AUTH"))],
)
async def verify_email(
    payload: VerifyEmailRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> OnboardingStateResponse:
    """Validates 6-digit email code and marks user as verified."""
    return await onboarding_service.verify_email(db=db, user=current_user, code=payload.code)


@router.post(
    "/resend-code",
    response_model=ResendCodeResponse,
    status_code=status.HTTP_200_OK,
    summary="Resend Verification Code",
    dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60, tier="AUTH"))],
)
async def resend_verification_code(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ResendCodeResponse:
    """Dispatches a new 6-digit verification code."""
    return await onboarding_service.resend_code(db=db, user=current_user)


@router.post(
    "/workspace",
    response_model=OnboardingStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Configure Initial Workspace",
    dependencies=[Depends(rate_limit(max_requests=20, window_seconds=60, tier="AUTH"))],
)
async def configure_workspace(
    payload: WorkspaceConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> OnboardingStateResponse:
    """Configures workspace name and presentation currency."""
    return await onboarding_service.configure_workspace(
        db=db,
        user=current_user,
        workspace_name=payload.workspace_name,
        default_currency=payload.default_currency,
        experience_level=payload.experience_level,
    )


@router.post(
    "/pair-initiate",
    response_model=PairInitiateResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate Onboarding MT5 Pairing",
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, tier="PAIRING"))],
)
async def initiate_onboarding_pairing(
    payload: PairInitiateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> PairInitiateResponse:
    """Generates an ephemeral 15-minute pairing token with guided MT5 instructions."""
    ip, ua = get_client_metadata(request)
    return await onboarding_service.initiate_pairing(
        db=db,
        user=current_user,
        account_number=payload.account_number,
        server_name=payload.server_name,
        ip_address=ip,
        user_agent=ua,
    )


@router.get(
    "/sync-status",
    response_model=SyncStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Poll Initial Connector & Sync Status",
    dependencies=[Depends(rate_limit(max_requests=120, window_seconds=60, tier="DASHBOARD"))],
)
async def poll_sync_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> SyncStatusResponse:
    """Polls real-time state of the initial Exness MT5 connector handshake and historical sync."""
    return await onboarding_service.get_sync_status(db=db, user=current_user)


@router.post(
    "/complete",
    response_model=CompleteOnboardingResponse,
    status_code=status.HTTP_200_OK,
    summary="Complete Onboarding Workflow",
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, tier="AUTH"))],
)
async def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> CompleteOnboardingResponse:
    """Marks onboarding as complete and provides the dashboard entry redirect."""
    return await onboarding_service.complete_onboarding(db=db, user=current_user)
