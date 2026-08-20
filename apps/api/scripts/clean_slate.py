import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text
from src.core.database import async_session_factory

async def clean_slate():
    async with async_session_factory() as db:
        await db.execute(text("DELETE FROM devices"))
        await db.execute(text("DELETE FROM pairing_tokens"))
        await db.execute(text("DELETE FROM account_sync_states"))
        await db.execute(text("DELETE FROM account_display_settings"))
        await db.execute(text("DELETE FROM raw_event_observations"))
        await db.execute(text("DELETE FROM raw_account_snapshots"))
        await db.execute(text("DELETE FROM raw_position_snapshots"))
        await db.execute(text("DELETE FROM canonical_trades"))
        await db.execute(text("DELETE FROM canonical_executions"))
        await db.execute(text("DELETE FROM canonical_balance_events"))
        await db.execute(text("DELETE FROM canonical_ledger_transactions"))
        await db.execute(text("DELETE FROM canonical_ledger_postings"))
        await db.execute(text("DELETE FROM canonical_trade_execution_map"))
        await db.execute(text("DELETE FROM analytics_snapshots"))
        await db.execute(text("DELETE FROM trading_dna_profiles"))
        await db.execute(text("DELETE FROM behavioral_patterns"))
        await db.execute(text("DELETE FROM reconciliation_runs"))
        await db.commit()
        print("Database cleaned to a 100% fresh slate!")

if __name__ == "__main__":
    asyncio.run(clean_slate())
