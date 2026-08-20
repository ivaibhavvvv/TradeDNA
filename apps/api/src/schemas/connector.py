import uuid
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field


# --- Pairing & Handshake Schemas ---

class PairingTokenCreateRequest(BaseModel):
    account_number: Optional[int] = None
    server_name: Optional[str] = None


class PairingTokenResponse(BaseModel):
    pairing_token: str
    expires_at: datetime
    expires_in_seconds: int = 300


class HandshakeExchangeRequest(BaseModel):
    pairing_token: str = Field(..., min_length=32, max_length=128)
    client_nonce: str = Field(..., min_length=16, max_length=64)
    broker: str = Field(default="EXNESS")
    account_number: int
    server_name: str
    trade_mode: str  # REAL or DEMO
    currency: str
    terminal_build: int = 0
    connector_version: str = "1.0.0"


class HandshakeExchangeResponse(BaseModel):
    device_id: uuid.UUID
    device_secret: str
    broker: str
    account_number: int
    server_name: str
    trade_mode: str
    currency: str
    sync_cursor_time_msc: int = 0
    sync_cursor_deal_ticket: int = 0


# --- Data Contract Schemas A through H ---

class HeartbeatPayload(BaseModel):
    schema_version: str = "1.0.0"
    connector_id: str
    account_number: int
    server_name: str
    terminal_build: int
    connector_version: str
    timestamp: str
    ping_latency_ms: Optional[float] = 0.0


class AccountSnapshotPayload(BaseModel):
    schema_version: str = "1.0.0"
    connector_id: str
    account_number: int
    currency: str
    balance: str
    equity: str
    margin: str
    margin_free: str
    margin_level: str
    leverage: int
    trade_mode: str
    is_hedging: bool = True
    snapshot_time: str


class PositionItem(BaseModel):
    position_ticket: int
    symbol: str
    position_type: str
    volume: str
    price_open: str
    price_current: str
    sl: str = "0.000000"
    tp: str = "0.000000"
    profit: str
    swap: str = "0.0000"
    open_time: str
    open_time_msc: Optional[int] = 0
    magic: Optional[int] = 0
    comment: Optional[str] = ""


class PositionSnapshotPayload(BaseModel):
    schema_version: str = "1.0.0"
    connector_id: str
    account_number: int
    positions: List[PositionItem] = []
    snapshot_time: str


class OrderEventPayload(BaseModel):
    schema_version: str = "1.0.0"
    observation_id: str
    event_id: str
    connector_id: str
    account_number: int
    order_ticket: int
    position_ticket: Optional[int] = 0
    symbol: str
    order_type: str
    order_state: str
    volume_initial: str
    volume_current: str
    price_open: str
    sl: str = "0.000000"
    tp: str = "0.000000"
    setup_time: str
    setup_time_msc: int
    done_time: Optional[str] = None
    done_time_msc: Optional[int] = 0
    order_magic: Optional[int] = 0
    order_reason: Optional[str] = "ORDER_REASON_CLIENT"
    order_external_id: Optional[str] = ""
    source_type: str = "EVENT_STREAM"
    raw_payload: Optional[dict[str, Any]] = None


class DealEventPayload(BaseModel):
    schema_version: str = "1.0.0"
    observation_id: str
    event_id: str
    connector_id: str
    account_number: int
    deal_ticket: int
    order_ticket: int
    position_ticket: Optional[int] = 0
    symbol: str
    deal_type: str  # BUY, SELL, BALANCE, CREDIT, COMMISSION, etc.
    deal_entry: str  # IN, OUT, INOUT, OUT_BY
    volume: str
    price: str
    commission: str = "0.0000"
    swap: str = "0.0000"
    fee: str = "0.0000"
    profit: str
    deal_time: str
    deal_time_msc: int
    deal_magic: Optional[int] = 0
    deal_reason: Optional[str] = "DEAL_REASON_CLIENT"
    deal_external_id: Optional[str] = ""
    source_type: str = "EVENT_STREAM"
    raw_payload: Optional[dict[str, Any]] = None


class HistoricalBatchSyncPayload(BaseModel):
    schema_version: str = "1.0.0"
    connector_id: str
    account_number: int
    sync_mode: str = "INITIAL_HISTORICAL"
    batch_index: int
    batch_size_deals: int
    batch_size_orders: int
    deals: List[DealEventPayload] = []
    orders: List[OrderEventPayload] = []
    from_timestamp: str
    from_time_msc: int
    to_timestamp: str
    to_time_msc: int
    is_final_batch: bool = False


class SyncStatusPayload(BaseModel):
    schema_version: str = "1.0.0"
    connector_id: str
    account_number: int
    sync_state: str
    last_synced_deal_ticket: int
    last_synced_time_msc: int
    total_deals_processed: int
    total_orders_processed: int
    pending_buffer_count: int = 0


class ErrorReportPayload(BaseModel):
    schema_version: str = "1.0.0"
    connector_id: str
    account_number: int
    error_code: str
    error_message: str
    mql5_last_error: int = 0
    occurred_at: str


class SyncRequestEnvelope(BaseModel):
    payload_type: str  # HEARTBEAT, SNAPSHOT_ACCOUNT, SNAPSHOT_POSITIONS, ORDER_EVENT, DEAL_EVENT, BATCH_HISTORICAL, SYNC_STATUS, ERROR_REPORT
    data: dict[str, Any]


class SyncResponse(BaseModel):
    success: bool = True
    status: str = "SYNCED"  # SYNCED, ACCEPTED, ACKNOWLEDGED, RESYNC_WINDOW
    acknowledged_time_msc: int = 0
    acknowledged_deal_ticket: int = 0
    message: str = "Payload durably processed"
