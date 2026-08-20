import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import delete, select
from src.core.database import async_session_factory
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
from src.models.user import User

async def test_purge_logic(account_number: int = 434120065):
    async with async_session_factory() as db:
        user_stmt = select(User).where(User.email == "vaibhav251001@gmail.com")
        res = await db.execute(user_stmt)
        user = res.scalar_one_or_none()
        if not user:
            print("User not found")
            return
        t_id = user.tenant_id

        print("Testing delete queries...")
        # 1. Analytics
        await db.execute(delete(AnalyticsSnapshot).where(AnalyticsSnapshot.tenant_id == t_id, AnalyticsSnapshot.account_number == account_number))
        await db.execute(delete(TradingDNAProfile).where(TradingDNAProfile.tenant_id == t_id, TradingDNAProfile.account_number == account_number))
        await db.execute(delete(BehavioralPattern).where(BehavioralPattern.tenant_id == t_id, BehavioralPattern.account_number == account_number))
        await db.execute(delete(AnalyticsFeatureStore).where(AnalyticsFeatureStore.tenant_id == t_id, AnalyticsFeatureStore.account_number == account_number))
        await db.execute(delete(BaselineComparison).where(BaselineComparison.tenant_id == t_id, BaselineComparison.account_number == account_number))

        # 2. Child Reconciliation Records
        await db.execute(delete(ReconciliationAccountSummary).where(ReconciliationAccountSummary.tenant_id == t_id, ReconciliationAccountSummary.account_number == account_number))
        await db.execute(delete(ReconciliationPositionSummary).where(ReconciliationPositionSummary.tenant_id == t_id, ReconciliationPositionSummary.account_number == account_number))
        await db.execute(delete(ReconciliationDiscrepancy).where(ReconciliationDiscrepancy.tenant_id == t_id, ReconciliationDiscrepancy.account_number == account_number))
        await db.execute(delete(RemediationProposal).where(RemediationProposal.tenant_id == t_id, RemediationProposal.account_number == account_number))
        await db.execute(delete(DataIntegrityScoreHistory).where(DataIntegrityScoreHistory.tenant_id == t_id, DataIntegrityScoreHistory.account_number == account_number))
        await db.execute(delete(ReconciliationRun).where(ReconciliationRun.tenant_id == t_id, ReconciliationRun.account_number == account_number))

        # 3. Canonical Ledger Records
        trade_ids_subquery = select(CanonicalTrade.id).where(CanonicalTrade.tenant_id == t_id, CanonicalTrade.account_number == account_number)
        await db.execute(delete(CanonicalTradeExecutionMap).where(CanonicalTradeExecutionMap.trade_id.in_(trade_ids_subquery)))

        tx_ids_subquery = select(CanonicalLedgerTransaction.id).where(CanonicalLedgerTransaction.tenant_id == t_id, CanonicalLedgerTransaction.account_number == account_number)
        await db.execute(delete(CanonicalLedgerPosting).where(CanonicalLedgerPosting.transaction_id.in_(tx_ids_subquery)))

        await db.execute(delete(CanonicalLedgerTransaction).where(CanonicalLedgerTransaction.tenant_id == t_id, CanonicalLedgerTransaction.account_number == account_number))
        await db.execute(delete(CanonicalTrade).where(CanonicalTrade.tenant_id == t_id, CanonicalTrade.account_number == account_number))
        await db.execute(delete(CanonicalExecution).where(CanonicalExecution.tenant_id == t_id, CanonicalExecution.account_number == account_number))
        await db.execute(delete(CanonicalBalanceEvent).where(CanonicalBalanceEvent.tenant_id == t_id, CanonicalBalanceEvent.account_number == account_number))
        await db.execute(delete(ReconstructionRun).where(ReconstructionRun.tenant_id == t_id, ReconstructionRun.account_number == account_number))

        # 4. Raw Ingress Snapshots & Events
        await db.execute(delete(RawEventObservation).where(RawEventObservation.tenant_id == t_id, RawEventObservation.account_number == account_number))
        await db.execute(delete(RawPositionSnapshot).where(RawPositionSnapshot.tenant_id == t_id, RawPositionSnapshot.account_number == account_number))
        await db.execute(delete(RawAccountSnapshot).where(RawAccountSnapshot.tenant_id == t_id, RawAccountSnapshot.account_number == account_number))

        # 5. Sync Gaps, Devices & Sync State
        await db.execute(delete(SyncGapEvent).where(SyncGapEvent.tenant_id == t_id, SyncGapEvent.account_number == account_number))
        await db.execute(delete(Device).where(Device.tenant_id == t_id, Device.account_number == account_number))
        await db.execute(delete(AccountDisplaySetting).where(AccountDisplaySetting.tenant_id == t_id, AccountDisplaySetting.account_number == account_number))
        await db.execute(delete(AccountSyncState).where(AccountSyncState.tenant_id == t_id, AccountSyncState.account_number == account_number))

        await db.commit()
        print("Purge queries executed successfully with 0 errors!")

if __name__ == "__main__":
    asyncio.run(test_purge_logic())
