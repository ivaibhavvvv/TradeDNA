import os
import asyncio
from collections.abc import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Force testing environment before importing settings
os.environ["ENVIRONMENT"] = "testing"

from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.rate_limit import rate_limiter
from src.main import app
import src.models
from src.models.base import Base

settings = get_settings()

from sqlalchemy.pool import StaticPool

TEST_DB_URL = "sqlite+aiosqlite:///file:testmemdb?mode=memory&cache=shared&uri=true"

test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False, "uri": True},
    poolclass=StaticPool,
    echo=False,
)
test_session_factory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_test_database():
    """Create in-memory database tables for each test and drop after."""
    rate_limiter.reset()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        yield session
        await session.commit()


app.dependency_overrides[get_db_session] = override_get_db_session


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
