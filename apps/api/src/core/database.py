from collections.abc import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.core.config import get_settings
from src.core.logging import logger

settings = get_settings()

# Configure engine options based on dialect
engine_kwargs = {"echo": settings.DEBUG}
if "sqlite" not in settings.DATABASE_URL:
    engine_kwargs.update({
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
        "pool_pre_ping": True,
    })

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    **engine_kwargs,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency providing an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_db_health() -> bool:
    """Readiness probe checking database connectivity."""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


async def init_db_schema() -> None:
    """Ensure all database tables and schema objects are created on startup."""
    try:
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
        import src.models.reconstruction_run

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to auto-initialize database schema: {e}")
