from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import and_, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.exceptions import ForbiddenException, NotFoundException
from src.models.account_settings import AccountDisplaySetting
from src.models.audit import AuditLog
from src.models.device import Device
from src.models.reconciliation import ReconciliationRun
from src.models.sync_state import AccountSyncState
from src.models.user import User
from src.schemas.connection import (
    AccountRevocationResponse,
    ConnectionAccountDTO,
    ConnectionDeviceDTO,
    ConnectionsOverviewResponse,
    DeviceRevocationResponse,
)


def mask_account_number(acc_num: int) -> str:
    """Masks account number preserving prefix and suffix."""
    s = str(acc_num)
    if len(s) <= 4:
        return f"***{s[-2:]}"
    return f"{s[:3]}****{s[-2:]}"


def mask_device_id(dev_id: uuid.UUID) -> str:
    """Masks device UUID for safe presentation."""
    s = str(dev_id)
    return f"dev_{s[:6]}...{s[-4:]}"


def calculate_freshness(last_sync: Optional[datetime], is_revoked: bool) -> tuple[Optional[int], str, str]:
    """Computes data freshness seconds, label, and overall connection status."""
    if is_revoked:
        return None, "Connector Revoked", "REVOKED"
    if not last_sync:
        return None, "Awaiting Initial Sync", "SYNCING"

    now = datetime.now(timezone.utc)
    if last_sync.tzinfo is None:
        last_sync = last_sync.replace(tzinfo=timezone.utc)

    delta_sec = max(0, int((now - last_sync).total_seconds()))

    if delta_sec < 10:
        return delta_sec, "Live (Synced just now)", "CONNECTED"
    elif delta_sec < 60:
        return delta_sec, f"Live (Synced {delta_sec}s ago)", "CONNECTED"
    elif delta_sec < 300:
        m = delta_sec // 60
        return delta_sec, f"Synced {m}m ago", "CONNECTED"
    elif delta_sec < 600:
        m = delta_sec // 60
        return delta_sec, f"Sync Delayed ({m}m ago)", "DEGRADED"
    else:
        m = delta_sec // 60
        return delta_sec, f"Data Stale ({m}m ago)", "STALE"


class ConnectionService:
    """Authoritative Connection Center business logic engine."""

    @classmethod
    async def get_overview(
        cls,
        db: AsyncSession,
        user: User,
    ) -> ConnectionsOverviewResponse:
        """Assembles aggregated Connection Center overview for the authenticated tenant."""
        # 1. Fetch Sync States
        stmt_sync = (
            select(AccountSyncState)
            .where(AccountSyncState.tenant_id == user.tenant_id)
            .order_by(desc(AccountSyncState.created_at))
        )
        res_sync = await db.execute(stmt_sync)
        sync_states = list(res_sync.scalars().all())
        existing_sync_accs = {s.account_number for s in sync_states}

        # 2. Fetch Display Settings
        stmt_disp = select(AccountDisplaySetting).where(AccountDisplaySetting.tenant_id == user.tenant_id)
        res_disp = await db.execute(stmt_disp)
        disp_map = {d.account_number: d for d in res_disp.scalars().all()}

        # 3. Fetch All Devices for Tenant
        stmt_dev = (
            select(Device)
            .where(Device.tenant_id == user.tenant_id)
            .order_by(desc(Device.last_seen_at))
        )
        res_dev = await db.execute(stmt_dev)
        all_devices = list(res_dev.scalars().all())

        # Include accounts that have active devices
        for dev in all_devices:
            if dev.account_number not in existing_sync_accs:
                synthetic_sync = AccountSyncState(
                    tenant_id=user.tenant_id,
                    account_number=dev.account_number,
                    broker=dev.broker or "EXNESS",
                    server_name=dev.server_name or "Exness",
                    currency=dev.currency or "USD",
                    trade_mode=dev.trade_mode or "DEMO",
                    sync_status="CONNECTED",
                    current_cursor_time_msc=dev.last_sync_time_msc or 0,
                    current_cursor_deal_ticket=dev.last_sync_deal_ticket or 0,
                    last_successful_sync_at=dev.last_seen_at or datetime.now(timezone.utc),
                )
                sync_states.append(synthetic_sync)
                existing_sync_accs.add(dev.account_number)

        devices_by_account: Dict[int, List[Device]] = {}
        for dev in all_devices:
            devices_by_account.setdefault(dev.account_number, []).append(dev)

        account_dtos: List[ConnectionAccountDTO] = []
        total_devices = len(all_devices)
        online_devices = 0
        stale_devices = 0

        for state in sync_states:
            disp = disp_map.get(state.account_number)
            if disp and disp.is_hidden:
                continue

            acc_devices = devices_by_account.get(state.account_number, [])
            device_dtos: List[ConnectionDeviceDTO] = []
            active_count = 0

            for dev in acc_devices:
                is_online = dev.is_active and not dev.is_revoked
                dev_status = "REVOKED" if dev.is_revoked else ("ONLINE" if dev.is_active else "OFFLINE")
                if is_online:
                    active_count += 1
                    online_devices += 1
                else:
                    stale_devices += 1

                device_dtos.append(
                    ConnectionDeviceDTO(
                        device_id=str(dev.id),
                        masked_device_id=mask_device_id(dev.id),
                        terminal_build=dev.terminal_build,
                        connector_version=dev.connector_version,
                        is_active=dev.is_active,
                        is_revoked=dev.is_revoked,
                        last_seen_at=dev.last_seen_at,
                        status=dev_status,
                    )
                )

            # Latest reconciliation report
            stmt_recon = (
                select(ReconciliationRun)
                .where(
                    ReconciliationRun.tenant_id == user.tenant_id,
                    ReconciliationRun.account_number == state.account_number,
                )
                .order_by(desc(ReconciliationRun.created_at))
            )
            res_recon = await db.execute(stmt_recon)
            recon_run = res_recon.scalars().first()

            all_revoked = len(acc_devices) > 0 and all(d.is_revoked for d in acc_devices)
            fresh_sec, fresh_label, conn_status = calculate_freshness(state.last_successful_sync_at, all_revoked)

            account_dtos.append(
                ConnectionAccountDTO(
                    account_number=state.account_number,
                    masked_account_number=mask_account_number(state.account_number),
                    display_name=disp.display_name if (disp and disp.display_name) else f"Exness #{mask_account_number(state.account_number)}",
                    broker=state.broker,
                    server_name=state.server_name,
                    currency=state.currency,
                    trade_mode=state.trade_mode,
                    account_status="ACTIVE" if not all_revoked else "REVOKED",
                    connection_status=conn_status,
                    devices_count=len(acc_devices),
                    active_devices_count=active_count,
                    devices=device_dtos,
                    last_heartbeat_at=acc_devices[0].last_seen_at if acc_devices else None,
                    last_successful_sync_at=state.last_successful_sync_at,
                    sync_status=state.sync_status,
                    current_cursor_time_msc=state.current_cursor_time_msc,
                    current_cursor_deal_ticket=state.current_cursor_deal_ticket,
                    historical_sync_status="COMPLETED" if state.current_cursor_deal_ticket > 0 else "INITIALIZING",
                    data_freshness_seconds=fresh_sec,
                    data_freshness_label=fresh_label,
                    integrity_score=recon_run.data_integrity_score if recon_run else None,
                    integrity_grade=recon_run.integrity_grade if recon_run else None,
                    last_reconciled_at=recon_run.created_at if recon_run else None,
                    unresolved_critical_discrepancies=recon_run.critical_count if recon_run else 0,
                    created_at=state.created_at,
                )
            )

        overall_freshness = "LIVE" if online_devices > 0 else ("OFFLINE" if total_devices > 0 else "NO_DEVICES")

        return ConnectionsOverviewResponse(
            total_accounts=len(account_dtos),
            total_devices=total_devices,
            online_devices=online_devices,
            stale_devices=stale_devices,
            overall_freshness=overall_freshness,
            accounts=account_dtos,
        )

    @classmethod
    async def get_account_detail(
        cls,
        db: AsyncSession,
        user: User,
        account_number: int,
    ) -> ConnectionAccountDTO:
        """Fetches detailed connection metadata for a single authorized account."""
        overview = await cls.get_overview(db, user)
        for acc in overview.accounts:
            if acc.account_number == account_number:
                return acc
        raise NotFoundException(f"Account #{account_number} not found or unauthorized for this tenant.")

    @classmethod
    async def revoke_device(
        cls,
        db: AsyncSession,
        user: User,
        device_id: uuid.UUID,
        ip_address: str = "",
        user_agent: str = "",
    ) -> DeviceRevocationResponse:
        """Revokes a specific connector device with tenant ownership verification."""
        stmt = select(Device).where(Device.id == device_id, Device.tenant_id == user.tenant_id)
        res = await db.execute(stmt)
        device = res.scalars().first()
        if not device:
            raise NotFoundException(f"Device {device_id} not found for this tenant.")

        device.is_active = False
        device.is_revoked = True
        db.add(device)

        # Audit event
        audit = AuditLog(
            id=uuid.uuid4(),
            tenant_id=user.tenant_id,
            user_id=user.id,
            event_type="DEVICE_REVOKED",
            ip_address=ip_address,
            user_agent=user_agent,
            payload={"device_id": str(device_id), "account_number": device.account_number},
        )
        db.add(audit)
        await db.commit()

        return DeviceRevocationResponse(
            status="REVOKED",
            device_id=str(device_id),
            revoked_at=datetime.now(timezone.utc),
            message="Connector device has been revoked and all ingress has been terminated.",
        )

    @classmethod
    async def revoke_all_devices(
        cls,
        db: AsyncSession,
        user: User,
        account_number: int,
        ip_address: str = "",
        user_agent: str = "",
    ) -> AccountRevocationResponse:
        """Revokes all connector devices for a specific account."""
        stmt = select(Device).where(Device.tenant_id == user.tenant_id, Device.account_number == account_number)
        res = await db.execute(stmt)
        devices = res.scalars().all()
        if not devices:
            raise NotFoundException(f"No devices found for account #{account_number}.")

        for dev in devices:
            dev.is_active = False
            dev.is_revoked = True
            db.add(dev)

        # Audit event
        audit = AuditLog(
            id=uuid.uuid4(),
            tenant_id=user.tenant_id,
            user_id=user.id,
            event_type="ACCOUNT_ALL_DEVICES_REVOKED",
            ip_address=ip_address,
            user_agent=user_agent,
            payload={"account_number": account_number, "devices_count": len(devices)},
        )
        db.add(audit)
        await db.commit()

        return AccountRevocationResponse(
            status="REVOKED",
            account_number=account_number,
            devices_revoked_count=len(devices),
            message=f"All {len(devices)} devices for account #{account_number} have been revoked.",
        )

    @classmethod
    async def update_display_name(
        cls,
        db: AsyncSession,
        user: User,
        account_number: int,
        display_name: str,
    ) -> ConnectionAccountDTO:
        """Updates or sets local display label for an account."""
        stmt = select(AccountDisplaySetting).where(
            AccountDisplaySetting.tenant_id == user.tenant_id,
            AccountDisplaySetting.account_number == account_number,
        )
        res = await db.execute(stmt)
        disp = res.scalars().first()

        if not disp:
            disp = AccountDisplaySetting(
                id=uuid.uuid4(),
                tenant_id=user.tenant_id,
                account_number=account_number,
                display_name=display_name.strip(),
                is_hidden=False,
            )
            db.add(disp)
        else:
            disp.display_name = display_name.strip()
            disp.is_hidden = False
            db.add(disp)

        await db.commit()
        return await cls.get_account_detail(db, user, account_number)

    @classmethod
    async def soft_delete_account(
        cls,
        db: AsyncSession,
        user: User,
        account_number: int,
    ) -> Dict[str, Any]:
        """Soft-hides account from UI while keeping immutable historical financial ledger intact."""
        stmt = select(AccountDisplaySetting).where(
            AccountDisplaySetting.tenant_id == user.tenant_id,
            AccountDisplaySetting.account_number == account_number,
        )
        res = await db.execute(stmt)
        disp = res.scalars().first()

        if not disp:
            disp = AccountDisplaySetting(
                id=uuid.uuid4(),
                tenant_id=user.tenant_id,
                account_number=account_number,
                display_name="",
                is_hidden=True,
            )
            db.add(disp)
        else:
            disp.is_hidden = True
            db.add(disp)

        await db.commit()
        return {"status": "HIDDEN", "account_number": account_number, "message": "Account removed from active view."}

    @classmethod
    async def purge_account(
        cls,
        db: AsyncSession,
        user: User,
        account_number: int,
        ip_address: str = "",
        user_agent: str = "",
    ) -> Dict[str, Any]:
        """Completely and permanently purges an account and all its associated data for the tenant."""
        from sqlalchemy import delete
        from src.models.device import Device
        from src.models.sync_state import AccountSyncState, SyncGapEvent
        from src.models.account_settings import AccountDisplaySetting
        from src.models.raw_event import RawEventObservation, RawAccountSnapshot, RawPositionSnapshot
        from src.models.canonical_ledger import (
            CanonicalTrade,
            CanonicalExecution,
            CanonicalBalanceEvent,
            CanonicalLedgerTransaction,
            CanonicalLedgerPosting,
            CanonicalTradeExecutionMap,
        )
        from src.models.reconstruction_run import ReconstructionRun
        from src.models.reconciliation import (
            ReconciliationRun,
            ReconciliationAccountSummary,
            ReconciliationPositionSummary,
            ReconciliationDiscrepancy,
            RemediationProposal,
            DataIntegrityScoreHistory,
        )
        from src.models.analytics import (
            AnalyticsSnapshot,
            TradingDNAProfile,
            BehavioralPattern,
            AnalyticsFeatureStore,
            BaselineComparison,
        )
        from src.models.alert import OperationalAlert
        from src.services.audit_service import log_security_event

        t_id = user.tenant_id

        # 1. Delete Analytics & Behavioral Profiles
        await db.execute(delete(AnalyticsSnapshot).where(AnalyticsSnapshot.tenant_id == t_id, AnalyticsSnapshot.account_number == account_number))
        await db.execute(delete(TradingDNAProfile).where(TradingDNAProfile.tenant_id == t_id, TradingDNAProfile.account_number == account_number))
        await db.execute(delete(BehavioralPattern).where(BehavioralPattern.tenant_id == t_id, BehavioralPattern.account_number == account_number))
        await db.execute(delete(AnalyticsFeatureStore).where(AnalyticsFeatureStore.tenant_id == t_id, AnalyticsFeatureStore.account_number == account_number))
        await db.execute(delete(BaselineComparison).where(BaselineComparison.tenant_id == t_id, BaselineComparison.account_number == account_number))

        # 2. Delete Child Reconciliation Records
        await db.execute(delete(ReconciliationAccountSummary).where(ReconciliationAccountSummary.tenant_id == t_id, ReconciliationAccountSummary.account_number == account_number))
        await db.execute(delete(ReconciliationPositionSummary).where(ReconciliationPositionSummary.tenant_id == t_id, ReconciliationPositionSummary.account_number == account_number))
        await db.execute(delete(ReconciliationDiscrepancy).where(ReconciliationDiscrepancy.tenant_id == t_id, ReconciliationDiscrepancy.account_number == account_number))
        await db.execute(delete(RemediationProposal).where(RemediationProposal.tenant_id == t_id, RemediationProposal.account_number == account_number))
        await db.execute(delete(DataIntegrityScoreHistory).where(DataIntegrityScoreHistory.tenant_id == t_id, DataIntegrityScoreHistory.account_number == account_number))
        await db.execute(delete(ReconciliationRun).where(ReconciliationRun.tenant_id == t_id, ReconciliationRun.account_number == account_number))

        # 3. Delete Canonical Ledger Records
        trade_ids_subquery = select(CanonicalTrade.id).where(CanonicalTrade.tenant_id == t_id, CanonicalTrade.account_number == account_number)
        await db.execute(delete(CanonicalTradeExecutionMap).where(CanonicalTradeExecutionMap.trade_id.in_(trade_ids_subquery)))

        tx_ids_subquery = select(CanonicalLedgerTransaction.id).where(CanonicalLedgerTransaction.tenant_id == t_id, CanonicalLedgerTransaction.account_number == account_number)
        await db.execute(delete(CanonicalLedgerPosting).where(CanonicalLedgerPosting.transaction_id.in_(tx_ids_subquery)))

        await db.execute(delete(CanonicalLedgerTransaction).where(CanonicalLedgerTransaction.tenant_id == t_id, CanonicalLedgerTransaction.account_number == account_number))
        await db.execute(delete(CanonicalTrade).where(CanonicalTrade.tenant_id == t_id, CanonicalTrade.account_number == account_number))
        await db.execute(delete(CanonicalExecution).where(CanonicalExecution.tenant_id == t_id, CanonicalExecution.account_number == account_number))
        await db.execute(delete(CanonicalBalanceEvent).where(CanonicalBalanceEvent.tenant_id == t_id, CanonicalBalanceEvent.account_number == account_number))
        await db.execute(delete(ReconstructionRun).where(ReconstructionRun.tenant_id == t_id, ReconstructionRun.account_number == account_number))

        # 4. Delete Raw Ingress Snapshots & Events
        await db.execute(delete(RawEventObservation).where(RawEventObservation.tenant_id == t_id, RawEventObservation.account_number == account_number))
        await db.execute(delete(RawPositionSnapshot).where(RawPositionSnapshot.tenant_id == t_id, RawPositionSnapshot.account_number == account_number))
        await db.execute(delete(RawAccountSnapshot).where(RawAccountSnapshot.tenant_id == t_id, RawAccountSnapshot.account_number == account_number))

        # 5. Delete Sync Gaps, Devices & Sync State
        await db.execute(delete(SyncGapEvent).where(SyncGapEvent.tenant_id == t_id, SyncGapEvent.account_number == account_number))
        await db.execute(delete(Device).where(Device.tenant_id == t_id, Device.account_number == account_number))
        await db.execute(delete(AccountDisplaySetting).where(AccountDisplaySetting.tenant_id == t_id, AccountDisplaySetting.account_number == account_number))
        await db.execute(delete(AccountSyncState).where(AccountSyncState.tenant_id == t_id, AccountSyncState.account_number == account_number))

        # 6. Audit Logging
        await log_security_event(
            db=db,
            event_type="account_purged_completely",
            ip_address=ip_address,
            user_agent=user_agent,
            tenant_id=user.tenant_id,
            user_id=user.id,
            payload={"account_number": account_number, "action": "FULL_PURGE"},
        )

        await db.commit()
        return {
            "status": "PURGED",
            "account_number": account_number,
            "message": f"Account #{account_number} and all associated data have been permanently removed.",
        }


connection_service = ConnectionService()
