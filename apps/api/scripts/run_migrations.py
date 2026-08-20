#!/usr/bin/env python3
"""
TradeDNA Production Database Migration Runner
Safely verifies database connectivity, applies Alembic migrations up to head,
and validates migration state without data loss.
"""

import os
import sys
import logging
from pathlib import Path
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migration_runner")


def get_alembic_config() -> Config:
    api_dir = Path(__file__).resolve().parent.parent
    ini_path = api_dir / "alembic.ini"
    if not ini_path.exists():
        raise FileNotFoundError(f"Alembic configuration not found at {ini_path}")

    config = Config(str(ini_path))
    config.set_main_option("script_location", str(api_dir / "alembic"))
    return config


def verify_database_connection(sync_url: str) -> bool:
    """Verifies that the target database is reachable and accepting queries."""
    try:
        engine = create_engine(sync_url, connect_args={"connect_timeout": 10} if "postgresql" in sync_url else {})
        with engine.connect() as conn:
            res = conn.execute(text("SELECT 1")).scalar()
            if res == 1:
                logger.info("Database connectivity verified.")
                return True
        return False
    except Exception as e:
        logger.error(f"Database connection verification failed: {e}")
        return False


def run_migrations() -> bool:
    """Executes database migrations up to the latest revision."""
    from src.core.config import get_settings
    settings = get_settings()

    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite"):
        sync_url = db_url.replace("sqlite+aiosqlite", "sqlite")
    else:
        sync_url = settings.DATABASE_URL_SYNC or db_url.replace("postgresql+asyncpg", "postgresql+psycopg2")

    logger.info("Verifying database connectivity before running migrations...")
    if not verify_database_connection(sync_url):
        logger.error("Target database is not reachable. Aborting migration.")
        return False

    config = get_alembic_config()
    config.set_main_option("sqlalchemy.url", sync_url)

    try:
        logger.info("Applying Alembic migrations up to 'head'...")
        command.upgrade(config, "head")
        logger.info("Alembic migrations applied successfully.")

        # Verify current revision
        engine = create_engine(sync_url)
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()
            script_dir = ScriptDirectory.from_config(config)
            head_rev = script_dir.get_current_head()

            logger.info(f"Current DB Revision: {current_rev}, Target Head: {head_rev}")
            if current_rev == head_rev:
                logger.info("Database migration state verified: DB is at HEAD.")
                return True
            else:
                logger.warning(f"DB revision ({current_rev}) does not match head ({head_rev}).")
                return False
    except Exception as e:
        logger.exception(f"Migration execution failed: {e}")
        return False


if __name__ == "__main__":
    success = run_migrations()
    sys.exit(0 if success else 1)
