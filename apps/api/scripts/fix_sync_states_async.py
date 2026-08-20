import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from src.core.database import async_session_factory
from src.models.device import Device
from src.models.sync_state import AccountSyncState

async def main():
    async with async_session_factory() as session:
        dev_res = await session.execute(select(Device))
        devices = dev_res.scalars().all()
        
        seen_accounts = set()
        for dev in devices:
            key = (dev.tenant_id, dev.account_number)
            if key in seen_accounts:
                continue
            seen_accounts.add(key)
            
            stmt = select(AccountSyncState).where(
                AccountSyncState.tenant_id == dev.tenant_id,
                AccountSyncState.account_number == dev.account_number
            )
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            if not existing:
                print(f"Adding AccountSyncState for account {dev.account_number}...")
                sync = AccountSyncState(
                    id=uuid.uuid4(),
                    tenant_id=dev.tenant_id,
                    account_number=dev.account_number,
                    broker=dev.broker or "EXNESS",
                    server_name=dev.server_name or "Exness",
                    currency=dev.currency or "USD",
                    trade_mode=dev.trade_mode or "DEMO",
                    sync_status="CONNECTED",
                    current_cursor_time_msc=0,
                    current_cursor_deal_ticket=0,
                    last_successful_sync_at=dev.last_seen_at or datetime.now(timezone.utc),
                    last_synced_device_id=dev.id,
                )
                session.add(sync)
            else:
                print(f"Account {dev.account_number} already has AccountSyncState.")
        await session.commit()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
