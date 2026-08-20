import hashlib
import json
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.exceptions import ForbiddenException, NotFoundException, UnauthorizedException, ValidationException
from src.models.device import Device, PairingToken
from src.models.raw_event import RawEventObservation
from src.models.sync_state import AccountSyncState
from src.models.user import User
from src.schemas.connector import (
    HandshakeExchangeRequest,
    HandshakeExchangeResponse,
    PairingTokenResponse,
    SyncRequestEnvelope,
    SyncResponse,
)
from src.services.audit_service import log_security_event


class ConnectorService:
    @staticmethod
    async def create_pairing_token(
        db: AsyncSession,
        current_user: User,
        ip_address: str,
        user_agent: str,
    ) -> PairingTokenResponse:
        """Create a single-use 64-char pairing token with 5-minute expiration."""
        raw_token = secrets.token_hex(32)  # 64 hex characters
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        pairing_record = PairingToken(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            token_hash=token_hash,
            is_used=False,
            expires_at=expires_at,
        )
        db.add(pairing_record)
        await db.flush()

        await log_security_event(
            db=db,
            event_type="connector_pairing_initiated",
            ip_address=ip_address,
            user_agent=user_agent,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            payload={"expires_in_seconds": 300},
        )

        return PairingTokenResponse(
            pairing_token=raw_token,
            expires_at=expires_at,
            expires_in_seconds=300,
        )

    @staticmethod
    async def exchange_pairing_token(
        db: AsyncSession,
        req: HandshakeExchangeRequest,
        ip_address: str,
        user_agent: str,
    ) -> HandshakeExchangeResponse:
        """
        Exchange a valid, single-use pairing token for a durable device_id and device_secret.
        Registers the connector device with strict 5-tuple broker identity binding.
        """
        token_hash = hashlib.sha256(req.pairing_token.strip().encode("utf-8")).hexdigest()
        token_stmt = select(PairingToken).where(PairingToken.token_hash == token_hash)
        token_res = await db.execute(token_stmt)
        token_record = token_res.scalar_one_or_none()

        if not token_record:
            raise UnauthorizedException("Invalid or unrecognized pairing token.")

        if token_record.is_used:
            raise UnauthorizedException("Pairing token has already been used.")

        now = datetime.now(timezone.utc)
        expires_at = token_record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < now:
            raise UnauthorizedException("Pairing token has expired. Please generate a fresh token.")

        # Strict Broker and Account Identity Validation
        if not req.broker or req.broker.upper() != "EXNESS":
            await log_security_event(
                db=db,
                event_type="connector_pairing_rejected",
                ip_address=ip_address,
                user_agent=user_agent,
                tenant_id=token_record.tenant_id,
                user_id=token_record.user_id,
                payload={"reason": "unsupported_broker", "broker": req.broker},
            )
            raise ValidationException(f"TradeDNA exclusively supports Exness MT5 terminals. Broker '{req.broker}' is not supported.")

        if req.account_number <= 0:
            await log_security_event(
                db=db,
                event_type="connector_pairing_rejected",
                ip_address=ip_address,
                user_agent=user_agent,
                tenant_id=token_record.tenant_id,
                user_id=token_record.user_id,
                payload={"reason": "invalid_account_number", "account_number": req.account_number},
            )
            raise ValidationException("Invalid Exness account number.")

        if not req.server_name or not req.server_name.strip():
            await log_security_event(
                db=db,
                event_type="connector_pairing_rejected",
                ip_address=ip_address,
                user_agent=user_agent,
                tenant_id=token_record.tenant_id,
                user_id=token_record.user_id,
                payload={"reason": "invalid_server_name"},
            )
            raise ValidationException("Invalid or missing Exness server name.")

        # Mark pairing token as consumed
        token_record.is_used = True

        # Generate 256-bit high-entropy device secret
        raw_device_secret = secrets.token_hex(32)  # 64 hex chars (32 bytes)
        secret_hash = hashlib.sha256(raw_device_secret.encode("utf-8")).hexdigest()

        # Create Device Record
        device = Device(
            tenant_id=token_record.tenant_id,
            device_secret_hash=secret_hash,
            device_secret=raw_device_secret,
            broker="EXNESS",
            account_number=req.account_number,
            server_name=req.server_name.strip(),
            trade_mode=req.trade_mode.upper(),
            currency=req.currency.upper(),
            terminal_build=req.terminal_build,
            connector_version=req.connector_version,
            is_active=True,
            is_revoked=False,
            last_seen_at=now,
            last_sync_time_msc=0,
            last_sync_deal_ticket=0,
        )
        db.add(device)
        await db.flush()

        await log_security_event(
            db=db,
            event_type="connector_pairing_completed",
            ip_address=ip_address,
            user_agent=user_agent,
            tenant_id=token_record.tenant_id,
            user_id=token_record.user_id,
            payload={
                "device_id": str(device.id),
                "account_number": req.account_number,
                "server_name": req.server_name,
            },
        )

        await log_security_event(
            db=db,
            event_type="connector_device_registered",
            ip_address=ip_address,
            user_agent=user_agent,
            tenant_id=token_record.tenant_id,
            user_id=token_record.user_id,
            payload={
                "device_id": str(device.id),
                "account_number": req.account_number,
                "server_name": req.server_name,
            },
        )

        return HandshakeExchangeResponse(
            device_id=device.id,
            device_secret=raw_device_secret,
            broker="EXNESS",
            account_number=req.account_number,
            server_name=req.server_name,
            trade_mode=req.trade_mode.upper(),
            currency=req.currency.upper(),
            sync_cursor_time_msc=0,
            sync_cursor_deal_ticket=0,
        )

    @staticmethod
    async def revoke_device(
        db: AsyncSession,
        device_id: uuid.UUID,
        current_user: User,
        ip_address: str,
        user_agent: str,
    ) -> dict:
        """Revoke a connector device permanently."""
        device_stmt = select(Device).where(
            Device.id == device_id,
            Device.tenant_id == current_user.tenant_id,
        )
        device_res = await db.execute(device_stmt)
        device = device_res.scalar_one_or_none()

        if not device:
            raise NotFoundException("Connector device not found.")

        device.is_revoked = True
        device.is_active = False

        await log_security_event(
            db=db,
            event_type="connector_device_revoked",
            ip_address=ip_address,
            user_agent=user_agent,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            payload={"device_id": str(device.id)},
        )

        return {"success": True, "message": "Device revoked successfully."}

    @staticmethod
    async def process_sync_payload(
        db: AsyncSession,
        device: Device,
        envelope: SyncRequestEnvelope,
        raw_body_bytes: bytes,
    ) -> SyncResponse:
        from src.services.raw_ingestion_service import RawIngestionService

        ack_time_msc, ack_deal_ticket, status_str = await RawIngestionService.process_sync_envelope(
            session=db,
            device=device,
            raw_body_bytes=raw_body_bytes,
            parsed_payload={"payload_type": envelope.payload_type, "data": envelope.data},
        )

        return SyncResponse(
            success=True,
            status=status_str,
            acknowledged_time_msc=ack_time_msc,
            acknowledged_deal_ticket=ack_deal_ticket,
            message="Payload durably processed and persisted in Layer 1 store",
        )


connector_service = ConnectorService()
