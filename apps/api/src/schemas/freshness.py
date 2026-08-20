from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class SyncTelemetryDTO(BaseModel):
    has_account: bool = True
    account_number: Optional[int] = None
    masked_account_number: Optional[str] = None
    server_name: Optional[str] = None
    currency: str = "USD"
    freshness_state: str = "UNKNOWN"
    # LIVE, SYNCING, RECOVERING, DEGRADED, STALE, OFFLINE, REVOKED, ERROR, UNKNOWN
    freshness_seconds: Optional[int] = None
    freshness_label: str = "Awaiting Sync Telemetry"
    sync_status: str = "INITIALIZING"
    is_connected: bool = False
    is_revoked: bool = False
    last_heartbeat_at: Optional[datetime] = None
    last_successful_sync_at: Optional[datetime] = None
    source_snapshot_at: Optional[datetime] = None
    calculated_at: datetime = Field(default_factory=datetime.utcnow)
    current_cursor_deal_ticket: int = 0
    current_cursor_time_msc: int = 0
    historical_sync_progress: int = 100  # 0 to 100
    sync_stage: str = "READY"  # CONNECTING, DISCOVERING_ACCOUNT, DOWNLOADING_HISTORY, PROCESSING_EVENTS, RECONSTRUCTING, RECONCILING, ANALYZING, READY
    events_received: int = 0
    events_processed: int = 0
    positions_discovered: int = 0
    integrity_score: str = "100.00"
    integrity_grade: str = "AAA"
    trust_status: str = "TRUSTED"  # TRUSTED or DATA_TRUST_DEGRADED
    reconstruction_run_id: Optional[str] = None
    suggested_polling_interval_ms: int = 10000
