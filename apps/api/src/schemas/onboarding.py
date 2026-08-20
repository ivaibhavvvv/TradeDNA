from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class OnboardingStateResponse(BaseModel):
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    current_step: str
    is_completed: bool
    email_verified: bool
    workspace_name: Optional[str] = None
    default_currency: str = "USD"
    paired_account_number: Optional[int] = None
    paired_device_id: Optional[uuid.UUID] = None
    initial_sync_deal_count: int = 0
    initial_integrity_score: Optional[Decimal] = None
    step_metadata: Dict[str, Any] = Field(default_factory=dict)
    completed_at: Optional[datetime] = None


class VerifyEmailRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=16, description="6-digit email verification code")


class ResendCodeResponse(BaseModel):
    status: str = "SENT"
    message: str = "A new verification code has been dispatched."


class WorkspaceConfigRequest(BaseModel):
    workspace_name: str = Field(..., min_length=2, max_length=128)
    default_currency: str = Field(default="USD", min_length=3, max_length=10)
    experience_level: Optional[str] = Field(default="INTERMEDIATE")


class PairInitiateRequest(BaseModel):
    account_number: Optional[int] = Field(default=None, description="Optional target Exness account number")
    server_name: Optional[str] = Field(default="Exness-Real25", description="Target server cluster")


class PairInitiateResponse(BaseModel):
    pairing_token: str
    expires_in_seconds: int = 900
    instructions: Dict[str, Any] = Field(default_factory=dict)


class SyncStatusResponse(BaseModel):
    status: str  # AWAITING_HANDSHAKE, CONNECTED, SYNCING, VALIDATED, COMPLETED, ERROR
    account_number: Optional[int] = None
    server_name: Optional[str] = None
    currency: Optional[str] = "USD"
    balance: Optional[Decimal] = None
    equity: Optional[Decimal] = None
    deals_ingested: int = 0
    reconstruction_status: Optional[str] = None
    integrity_score: Optional[Decimal] = None
    integrity_grade: Optional[str] = None
    is_validated: bool = False
    details: Optional[str] = None


class CompleteOnboardingResponse(BaseModel):
    status: str = "COMPLETED"
    redirect_url: str = "/dashboard/overview"
    message: str = "Onboarding completed successfully. Welcome to TradeDNA."
