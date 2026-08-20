import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import all models to register with Base
from src.core.database import engine
from src.models.base import Base
import src.models.user
import src.models.tenant
import src.models.device
import src.models.raw_event
import src.models.canonical_ledger
import src.models.sync_state
import src.models.reconciliation
import src.models.analytics
import src.models.alert
import src.models.account_settings
import src.models.audit

async def init_tables():
    async with engine.begin() as conn:
        print("Creating all tables in database...")
        await conn.run_sync(Base.metadata.create_all)
        print("All tables created successfully!")

if __name__ == "__main__":
    asyncio.run(init_tables())
