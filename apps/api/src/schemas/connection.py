from datetime import datetime
from decimal import Decimal
from typing import List, Optional
import uuid
from pydantic import BaseModel, Field


class ConnectionDeviceDTO(BaseModel):
    device_id: str
    masked_device_id: str
    terminal_build: int
    connector_version: str
    is_active: bool
    is_revoked: bool
    last_seen_at: Optional[datetime] = None
    status: str = "OFFLINE"  # ONLINE, STALE, REVOKED, OFFLINE


class ConnectionAccountDTO(BaseModel):
    account_number: int
    masked_account_number: str
    display_name: str
    broker: str = "EXNESS"
    server_name: str
    currency: str = "USD"
    trade_mode: str = "REAL"
    account_status: str = "ACTIVE"
    connection_status: str = "CONNECTED"  # CONNECTED, SYNCING, STALE, DEGRADED, RECONNECTING, REVOKED, ERROR
    devices_count: int = 0
    active_devices_count: int = 0
    devices: List[ConnectionDeviceDTO] = Field(default_factory=list)
    last_heartbeat_at: Optional[datetime] = None
    last_successful_sync_at: Optional[datetime] = None
    sync_status: str = "INITIALIZING"
    current_cursor_time_msc: int = 0
    current_cursor_deal_ticket: int = 0
    historical_sync_status: str = "COMPLETED"
    data_freshness_seconds: Optional[int] = None
    data_freshness_label: str = "Data Freshness Pending"
    integrity_score: Optional[Decimal] = None
    integrity_grade: Optional[str] = None
    last_reconciled_at: Optional[datetime] = None
    unresolved_critical_discrepancies: int = 0
    created_at: Optional[datetime] = None


class ConnectionsOverviewResponse(BaseModel):
    total_accounts: int
    total_devices: int
    online_devices: int
    stale_devices: int
    overall_freshness: str
    accounts: List[ConnectionAccountDTO] = Field(default_factory=list)


class UpdateAccountDisplayNameRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=128)


class DeviceRevocationResponse(BaseModel):
    status: str = "REVOKED"
    device_id: str
    revoked_at: datetime
    message: str = "Connector device has been revoked and all ingress has been terminated."


class AccountRevocationResponse(BaseModel):
    status: str = "REVOKED"
    account_number: int
    devices_revoked_count: int
    message: str = "All devices for this account have been revoked."
