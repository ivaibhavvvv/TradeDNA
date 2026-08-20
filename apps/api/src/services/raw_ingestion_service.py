from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.exceptions import (
    ForbiddenException,
    TradeDNAException,
    UnauthorizedException,
    ValidationException,
)
from src.models.device import Device
from src.models.raw_event import (
    RawAccountSnapshot,
    RawEventObservation,
    RawIngressPayload,
    RawPositionSnapshot,
)
from src.models.sync_state import AccountSyncState, SyncGapEvent


class RawIngestionService:
    """Atomic, append-only Layer 1 ingestion service with deduplication,
    conflict detection, and cursor atomicity."""

    @staticmethod
    def compute_sha256(data_bytes: bytes) -> str:
        return hashlib.sha256(data_bytes).hexdigest().lower()

    @staticmethod
    def compute_json_hash(data_dict: dict[str, Any]) -> str:
        # Normalize by excluding observation envelope metadata so identical financial events match
        normalized = {k: v for k, v in data_dict.items() if k not in ("observation_id", "received_at", "received_at_utc")}
        canonical_json = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest().lower()

    @classmethod
    async def get_or_create_account_sync_state(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        broker: str,
        account_number: int,
        server_name: str,
        currency: str,
        trade_mode: str,
    ) -> AccountSyncState:
        stmt = select(AccountSyncState).where(
            AccountSyncState.tenant_id == tenant_id,
            AccountSyncState.broker == broker,
            AccountSyncState.account_number == account_number,
            AccountSyncState.server_name == server_name,
        )
        res = await session.execute(stmt)
        sync_state = res.scalar_one_or_none()

        if not sync_state:
            sync_state = AccountSyncState(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                broker=broker,
                account_number=account_number,
                server_name=server_name,
                currency=currency,
                trade_mode=trade_mode,
                sync_status="INITIALIZING",
                current_cursor_time_msc=0,
                current_cursor_deal_ticket=0,
            )
            session.add(sync_state)
            await session.flush()

        return sync_state

    @classmethod
    async def process_sync_envelope(
        cls,
        session: AsyncSession,
        device: Device,
        raw_body_bytes: bytes,
        parsed_payload: dict[str, Any],
    ) -> tuple[int, int, str]:
        """Atomically ingests exact raw HTTP bytes, extracts observed events,
        classifies duplicate/conflicting observations, and updates cursor."""
        payload_type = parsed_payload.get("payload_type", "UNKNOWN")
        data = parsed_payload.get("data", {})
        schema_version = data.get("schema_version", "1.0.0")

        if schema_version != "1.0.0":
            raise ValidationException(
                f"Unsupported schema version '{schema_version}'. Supported version is '1.0.0'."
            )

        # 1. 5-Tuple Identity Validation
        payload_acc = data.get("account_number", device.account_number)
        if payload_acc != device.account_number:
            raise ForbiddenException(
                f"ACCOUNT_IDENTITY_MISMATCH: payload account {payload_acc} != device account {device.account_number}"
            )

        payload_server = data.get("server_name", device.server_name)
        if payload_server and payload_server != device.server_name:
            raise ForbiddenException(
                f"SERVER_MISMATCH: payload server {payload_server} != device server {device.server_name}"
            )

        payload_currency = data.get("currency", device.currency)
        if payload_currency and payload_currency != device.currency:
            raise ForbiddenException(
                f"CURRENCY_MISMATCH: payload currency {payload_currency} != device currency {device.currency}"
            )

        payload_trade_mode = data.get("trade_mode", device.trade_mode)
        if payload_trade_mode and payload_trade_mode != device.trade_mode:
            raise ForbiddenException(
                f"TRADE_MODE_MISMATCH: payload trade mode {payload_trade_mode} != device trade mode {device.trade_mode}"
            )

        # 2. Get or Initialize Account Synchronization State
        sync_state = await cls.get_or_create_account_sync_state(
            session=session,
            tenant_id=device.tenant_id,
            broker=device.broker,
            account_number=device.account_number,
            server_name=device.server_name,
            currency=device.currency,
            trade_mode=device.trade_mode,
        )

        # 3. Create Layer 1 Raw Ingress Record
        payload_hash = cls.compute_sha256(raw_body_bytes)
        ingress_id = uuid.uuid4()
        raw_ingress = RawIngressPayload(
            id=ingress_id,
            tenant_id=device.tenant_id,
            device_id=device.id,
            account_number=device.account_number,
            server_name=device.server_name,
            payload_type=payload_type,
            schema_version=schema_version,
            payload_hash=payload_hash,
            raw_payload_bytes=raw_body_bytes,
            raw_payload_json=parsed_payload,
        )
        session.add(raw_ingress)

        now_utc = datetime.now(timezone.utc)
        highest_time_msc = sync_state.current_cursor_time_msc
        highest_deal_ticket = sync_state.current_cursor_deal_ticket

        # 4. Handle Payload Specific Ingestion
        if payload_type == "SNAPSHOT_ACCOUNT":
            snapshot = RawAccountSnapshot(
                id=uuid.uuid4(),
                ingress_payload_id=ingress_id,
                tenant_id=device.tenant_id,
                device_id=device.id,
                account_number=device.account_number,
                server_name=device.server_name,
                currency=data.get("currency", device.currency),
                balance=Decimal(str(data.get("balance", "0.0000"))),
                equity=Decimal(str(data.get("equity", "0.0000"))),
                margin=Decimal(str(data.get("margin", "0.0000"))),
                margin_free=Decimal(str(data.get("margin_free", "0.0000"))),
                margin_level=Decimal(str(data.get("margin_level", "0.00"))),
                leverage=int(data.get("leverage", 500)),
                trade_mode=data.get("trade_mode", device.trade_mode),
                is_hedging=bool(data.get("is_hedging", True)),
                raw_payload_json=data,
                snapshot_time_utc=now_utc,
            )
            session.add(snapshot)

        elif payload_type == "SNAPSHOT_POSITIONS":
            positions = data.get("positions", [])
            pos_snapshot = RawPositionSnapshot(
                id=uuid.uuid4(),
                ingress_payload_id=ingress_id,
                tenant_id=device.tenant_id,
                device_id=device.id,
                account_number=device.account_number,
                server_name=device.server_name,
                position_count=len(positions),
                raw_payload_json=data,
                snapshot_time_utc=now_utc,
            )
            session.add(pos_snapshot)

        elif payload_type == "DEAL_EVENT":
            ticket = int(data.get("deal_ticket", 0))
            t_msc = int(data.get("deal_time_msc", 0))
            obs_id = uuid.UUID(data["observation_id"]) if "observation_id" in data else uuid.uuid4()
            item_hash = cls.compute_json_hash(data)

            # Deduplication & Conflict Detection
            status = await cls._classify_observation(
                session=session,
                tenant_id=device.tenant_id,
                account_number=device.account_number,
                event_type="DEAL_EVENT",
                external_ticket=ticket,
                item_hash=item_hash,
                account_sync_id=sync_state.id,
                data=data,
            )

            obs = RawEventObservation(
                id=uuid.uuid4(),
                observation_id=obs_id,
                ingress_payload_id=ingress_id,
                tenant_id=device.tenant_id,
                device_id=device.id,
                account_number=device.account_number,
                server_name=device.server_name,
                source_type="ON_TRADE_TRANSACTION",
                event_type="DEAL_EVENT",
                external_ticket=ticket,
                external_event_id=data.get("deal_external_id"),
                item_payload_hash=item_hash,
                raw_item_json=data,
                observation_status=status,
                source_time_msc=t_msc,
                source_timestamp_utc=now_utc,
            )
            session.add(obs)

            if t_msc > highest_time_msc or (t_msc == highest_time_msc and ticket > highest_deal_ticket):
                highest_time_msc = t_msc
                highest_deal_ticket = ticket

        elif payload_type == "ORDER_EVENT":
            ticket = int(data.get("order_ticket", 0))
            t_msc = int(data.get("done_time_msc", data.get("setup_time_msc", 0)))
            obs_id = uuid.UUID(data["observation_id"]) if "observation_id" in data else uuid.uuid4()
            item_hash = cls.compute_json_hash(data)

            status = await cls._classify_observation(
                session=session,
                tenant_id=device.tenant_id,
                account_number=device.account_number,
                event_type="ORDER_EVENT",
                external_ticket=ticket,
                item_hash=item_hash,
                account_sync_id=sync_state.id,
                data=data,
            )

            obs = RawEventObservation(
                id=uuid.uuid4(),
                observation_id=obs_id,
                ingress_payload_id=ingress_id,
                tenant_id=device.tenant_id,
                device_id=device.id,
                account_number=device.account_number,
                server_name=device.server_name,
                source_type="ON_TRADE_TRANSACTION",
                event_type="ORDER_EVENT",
                external_ticket=ticket,
                external_event_id=data.get("order_external_id"),
                item_payload_hash=item_hash,
                raw_item_json=data,
                observation_status=status,
                source_time_msc=t_msc,
                source_timestamp_utc=now_utc,
            )
            session.add(obs)

        elif payload_type == "BATCH_HISTORICAL":
            deals = data.get("deals", [])
            orders = data.get("orders", [])
            source_type = data.get("sync_mode", "INITIAL_HISTORICAL")

            deal_tickets = [int(d["deal_ticket"]) for d in deals if "deal_ticket" in d]
            existing_deals = {}
            if deal_tickets:
                stmt_d = select(RawEventObservation).where(
                    RawEventObservation.tenant_id == device.tenant_id,
                    RawEventObservation.account_number == device.account_number,
                    RawEventObservation.event_type == "DEAL_EVENT",
                    RawEventObservation.external_ticket.in_(deal_tickets),
                )
                res_d = await session.execute(stmt_d)
                for row in res_d.scalars().all():
                    existing_deals[row.external_ticket] = row

            for deal_item in deals:
                d_ticket = int(deal_item.get("deal_ticket", 0))
                d_msc = int(deal_item.get("deal_time_msc", 0))
                d_obs_id = uuid.UUID(deal_item["observation_id"]) if "observation_id" in deal_item else uuid.uuid4()
                d_hash = cls.compute_json_hash(deal_item)

                if d_ticket not in existing_deals:
                    d_status = "ORIGINAL"
                elif existing_deals[d_ticket].item_payload_hash == d_hash:
                    d_status = "DUPLICATE"
                else:
                    d_status = "CONFLICTING"
                    gap_event = SyncGapEvent(
                        id=uuid.uuid4(),
                        tenant_id=device.tenant_id,
                        account_sync_id=sync_state.id,
                        account_number=device.account_number,
                        gap_classification="POSSIBLE_GAP",
                        anomaly_category="CONFLICTING_PAYLOAD",
                        evidence_details={
                            "external_ticket": d_ticket,
                            "event_type": "DEAL_EVENT",
                            "existing_observation_id": str(existing_deals[d_ticket].observation_id),
                            "existing_hash": existing_deals[d_ticket].item_payload_hash,
                            "new_hash": d_hash,
                        },
                    )
                    session.add(gap_event)
                    sync_state.detected_anomalies_count += 1
                    sync_state.sync_status = "GAP_DETECTED"

                obs = RawEventObservation(
                    id=uuid.uuid4(),
                    observation_id=d_obs_id,
                    ingress_payload_id=ingress_id,
                    tenant_id=device.tenant_id,
                    device_id=device.id,
                    account_number=device.account_number,
                    server_name=device.server_name,
                    source_type=source_type,
                    event_type="DEAL_EVENT",
                    external_ticket=d_ticket,
                    external_event_id=deal_item.get("deal_external_id"),
                    item_payload_hash=d_hash,
                    raw_item_json=deal_item,
                    observation_status=d_status,
                    source_time_msc=d_msc,
                    source_timestamp_utc=now_utc,
                )
                session.add(obs)

                if d_msc > highest_time_msc or (d_msc == highest_time_msc and d_ticket > highest_deal_ticket):
                    highest_time_msc = d_msc
                    highest_deal_ticket = d_ticket

            order_tickets = [int(o["order_ticket"]) for o in orders if "order_ticket" in o]
            existing_orders = {}
            if order_tickets:
                stmt_o = select(RawEventObservation).where(
                    RawEventObservation.tenant_id == device.tenant_id,
                    RawEventObservation.account_number == device.account_number,
                    RawEventObservation.event_type == "ORDER_EVENT",
                    RawEventObservation.external_ticket.in_(order_tickets),
                )
                res_o = await session.execute(stmt_o)
                for row in res_o.scalars().all():
                    existing_orders[row.external_ticket] = row

            for order_item in orders:
                o_ticket = int(order_item.get("order_ticket", 0))
                o_msc = int(order_item.get("done_time_msc", order_item.get("setup_time_msc", 0)))
                o_obs_id = uuid.UUID(order_item["observation_id"]) if "observation_id" in order_item else uuid.uuid4()
                o_hash = cls.compute_json_hash(order_item)

                if o_ticket not in existing_orders:
                    o_status = "ORIGINAL"
                elif existing_orders[o_ticket].item_payload_hash == o_hash:
                    o_status = "DUPLICATE"
                else:
                    o_status = "CONFLICTING"
                    gap_event = SyncGapEvent(
                        id=uuid.uuid4(),
                        tenant_id=device.tenant_id,
                        account_sync_id=sync_state.id,
                        account_number=device.account_number,
                        gap_classification="POSSIBLE_GAP",
                        anomaly_category="CONFLICTING_PAYLOAD",
                        evidence_details={
                            "external_ticket": o_ticket,
                            "event_type": "ORDER_EVENT",
                            "existing_observation_id": str(existing_orders[o_ticket].observation_id),
                            "existing_hash": existing_orders[o_ticket].item_payload_hash,
                            "new_hash": o_hash,
                        },
                    )
                    session.add(gap_event)
                    sync_state.detected_anomalies_count += 1
                    sync_state.sync_status = "GAP_DETECTED"

                obs = RawEventObservation(
                    id=uuid.uuid4(),
                    observation_id=o_obs_id,
                    ingress_payload_id=ingress_id,
                    tenant_id=device.tenant_id,
                    device_id=device.id,
                    account_number=device.account_number,
                    server_name=device.server_name,
                    source_type=source_type,
                    event_type="ORDER_EVENT",
                    external_ticket=o_ticket,
                    external_event_id=order_item.get("order_external_id"),
                    item_payload_hash=o_hash,
                    raw_item_json=order_item,
                    observation_status=o_status,
                    source_time_msc=o_msc,
                    source_timestamp_utc=now_utc,
                )
                session.add(obs)

        elif payload_type == "ERROR_REPORT":
            gap_event = SyncGapEvent(
                id=uuid.uuid4(),
                tenant_id=device.tenant_id,
                account_sync_id=sync_state.id,
                account_number=device.account_number,
                gap_classification="POSSIBLE_GAP",
                anomaly_category="CONNECTOR_ERROR_REPORT",
                evidence_details=data,
            )
            session.add(gap_event)
            sync_state.detected_anomalies_count += 1
            sync_state.sync_status = "DEGRADED"

        # 5. Cursor & State Atomicity Update in Same Transaction
        sync_state.current_cursor_time_msc = highest_time_msc
        sync_state.current_cursor_deal_ticket = highest_deal_ticket
        sync_state.last_synced_device_id = device.id
        sync_state.last_successful_sync_at = now_utc
        if sync_state.sync_status in ["INITIALIZING", "SYNCING", "STALE"]:
            sync_state.sync_status = "CURRENT"

        device.last_sync_time_msc = highest_time_msc
        device.last_sync_deal_ticket = highest_deal_ticket
        device.last_seen_at = now_utc

        await session.flush()
        return highest_time_msc, highest_deal_ticket, "SYNCED"

    @classmethod
    async def _classify_observation(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        account_number: int,
        event_type: str,
        external_ticket: int,
        item_hash: str,
        account_sync_id: uuid.UUID,
        data: dict[str, Any],
    ) -> str:
        """Classifies incoming observed event as ORIGINAL, DUPLICATE, or CONFLICTING."""
        stmt = select(RawEventObservation).where(
            RawEventObservation.tenant_id == tenant_id,
            RawEventObservation.account_number == account_number,
            RawEventObservation.event_type == event_type,
            RawEventObservation.external_ticket == external_ticket,
        ).limit(1)
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

        if not existing:
            return "ORIGINAL"

        if existing.item_payload_hash == item_hash:
            return "DUPLICATE"

        # Conflicting Observation: Same ticket, different payload hash!
        gap_event = SyncGapEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            account_sync_id=account_sync_id,
            account_number=account_number,
            gap_classification="POSSIBLE_GAP",
            anomaly_category="CONFLICTING_PAYLOAD",
            evidence_details={
                "external_ticket": external_ticket,
                "event_type": event_type,
                "existing_observation_id": str(existing.observation_id),
                "existing_hash": existing.item_payload_hash,
                "new_hash": item_hash,
                "existing_payload": existing.raw_item_json,
                "conflicting_payload": data,
            },
        )
        session.add(gap_event)

        # Flag account sync state as having anomalies
        sync_state_stmt = select(AccountSyncState).where(AccountSyncState.id == account_sync_id)
        s_res = await session.execute(sync_state_stmt)
        s = s_res.scalar_one_or_none()
        if s:
            s.detected_anomalies_count += 1
            s.sync_status = "GAP_DETECTED"

        return "CONFLICTING"
