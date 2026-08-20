from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import time
from typing import Any, Dict
import uuid
import httpx
from httpx import AsyncClient
import pytest
from sqlalchemy import select, update
from src.core.connector_auth import reset_nonce_cache
from src.core.database import get_db_session
from src.models.device import Device
from src.models.sync_state import AccountSyncState
from tests.test_phase8d_e2e_production import setup_production_test_environment


@pytest.mark.asyncio
async def test_sync_telemetry_live_state(async_client: AsyncClient):
    """Test 1: Verifies LIVE freshness state when connector synced recently."""
    account_number = 9940101
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number, server_name="Exness-Real25", currency="USD"
    )

    from tests.conftest import test_session_factory
    async with test_session_factory() as session:
        stmt = (
            update(AccountSyncState)
            .where(AccountSyncState.account_number == account_number)
            .values(sync_status="CURRENT", current_cursor_deal_ticket=500, last_successful_sync_at=datetime.now(timezone.utc))
        )
        await session.execute(stmt)
        await session.commit()

    resp = await async_client.get("/api/v1/dashboard/sync-telemetry", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["has_account"] is True
    assert data["account_number"] == account_number
    assert data["freshness_state"] == "LIVE"
    assert data["is_connected"] is True
    assert data["is_revoked"] is False
    assert data["suggested_polling_interval_ms"] in (5000, 10000)
    assert "Live" in data["freshness_label"]


@pytest.mark.asyncio
async def test_sync_telemetry_syncing_state(async_client: AsyncClient):
    """Test 2: Verifies SYNCING state during active historical or batch synchronization."""
    account_number = 9940201
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    # Set state to INITIALIZING / SYNCING with cursor 0
    from tests.conftest import test_session_factory
    async with test_session_factory() as session:
        stmt = (
            update(AccountSyncState)
            .where(AccountSyncState.account_number == account_number)
            .values(sync_status="SYNCING", current_cursor_deal_ticket=0)
        )
        await session.execute(stmt)
        await session.commit()

    resp = await async_client.get(
        f"/api/v1/dashboard/sync-telemetry?account_number={account_number}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["freshness_state"] == "SYNCING"
    assert data["historical_sync_progress"] == 65
    assert data["suggested_polling_interval_ms"] == 3000


@pytest.mark.asyncio
async def test_sync_telemetry_degraded_state(async_client: AsyncClient):
    """Test 3: Verifies DEGRADED state when last sync was between 2m and 10m ago."""
    account_number = 9940301
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    four_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=4)
    from tests.conftest import test_session_factory
    async with test_session_factory() as session:
        stmt = (
            update(AccountSyncState)
            .where(AccountSyncState.account_number == account_number)
            .values(sync_status="CURRENT", current_cursor_deal_ticket=500, last_successful_sync_at=four_mins_ago)
        )
        await session.execute(stmt)
        await session.commit()

    resp = await async_client.get(
        f"/api/v1/dashboard/sync-telemetry?account_number={account_number}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["freshness_state"] == "DEGRADED"
    assert "4m ago" in data["freshness_label"]
    assert data["suggested_polling_interval_ms"] == 15000


@pytest.mark.asyncio
async def test_sync_telemetry_stale_state(async_client: AsyncClient):
    """Test 4: Verifies STALE state when last sync was > 10m ago."""
    account_number = 9940401
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    fifteen_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
    from tests.conftest import test_session_factory
    async with test_session_factory() as session:
        stmt = (
            update(AccountSyncState)
            .where(AccountSyncState.account_number == account_number)
            .values(sync_status="CURRENT", current_cursor_deal_ticket=500, last_successful_sync_at=fifteen_mins_ago)
        )
        await session.execute(stmt)
        await session.commit()

    resp = await async_client.get(
        f"/api/v1/dashboard/sync-telemetry?account_number={account_number}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["freshness_state"] == "STALE"
    assert "15m ago" in data["freshness_label"]
    assert data["suggested_polling_interval_ms"] == 30000


@pytest.mark.asyncio
async def test_sync_telemetry_offline_state(async_client: AsyncClient):
    """Test 5: Verifies OFFLINE state when connector device is inactive."""
    account_number = 9940501
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    from tests.conftest import test_session_factory
    async with test_session_factory() as session:
        stmt = (
            update(Device)
            .where(Device.id == uuid.UUID(str(device_id)))
            .values(is_active=False)
        )
        await session.execute(stmt)
        stmt_sync = (
            update(AccountSyncState)
            .where(AccountSyncState.account_number == account_number)
            .values(sync_status="CURRENT", current_cursor_deal_ticket=500)
        )
        await session.execute(stmt_sync)
        await session.commit()

    resp = await async_client.get(
        f"/api/v1/dashboard/sync-telemetry?account_number={account_number}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["freshness_state"] == "OFFLINE"
    assert data["is_connected"] is False


@pytest.mark.asyncio
async def test_sync_telemetry_revoked_state(async_client: AsyncClient):
    """Test 6: Verifies REVOKED state and polling interval cutoff."""
    account_number = 9940601
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    from tests.conftest import test_session_factory
    async with test_session_factory() as session:
        stmt = (
            update(Device)
            .where(Device.id == uuid.UUID(str(device_id)))
            .values(is_active=False, is_revoked=True)
        )
        await session.execute(stmt)
        stmt_sync = (
            update(AccountSyncState)
            .where(AccountSyncState.account_number == account_number)
            .values(sync_status="CURRENT", current_cursor_deal_ticket=500)
        )
        await session.execute(stmt_sync)
        await session.commit()

    resp = await async_client.get(
        f"/api/v1/dashboard/sync-telemetry?account_number={account_number}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["freshness_state"] == "REVOKED"
    assert data["is_revoked"] is True
    assert data["suggested_polling_interval_ms"] == 0


@pytest.mark.asyncio
async def test_sync_telemetry_recovering_state(async_client: AsyncClient):
    """Test 7: Verifies RECOVERING state when sync recovery spool is draining."""
    account_number = 9940701
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    from tests.conftest import test_session_factory
    async with test_session_factory() as session:
        stmt = (
            update(AccountSyncState)
            .where(AccountSyncState.account_number == account_number)
            .values(sync_status="RECOVERING")
        )
        await session.execute(stmt)
        await session.commit()

    resp = await async_client.get(
        f"/api/v1/dashboard/sync-telemetry?account_number={account_number}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["freshness_state"] == "RECOVERING"
    assert data["suggested_polling_interval_ms"] == 3000


@pytest.mark.asyncio
async def test_sync_telemetry_cross_tenant_isolation(async_client: AsyncClient):
    """Test 8: Confirms cross-tenant query for sync telemetry returns HTTP 404 (zero leakage)."""
    account_a = 9940801
    auth_headers_a, _, _, _, _, _ = await setup_production_test_environment(async_client, account_a)

    account_b = 9940802
    auth_headers_b, _, _, _, _, _ = await setup_production_test_environment(async_client, account_b)

    # Tenant B tries to query Tenant A's account telemetry
    resp = await async_client.get(
        f"/api/v1/dashboard/sync-telemetry?account_number={account_a}",
        headers=auth_headers_b,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_manual_sync_trigger_workflow(async_client: AsyncClient):
    """Test 9: Verifies authorized manual sync trigger changes state to SYNCING."""
    account_number = 9940901
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    trig_resp = await async_client.post(
        "/api/v1/dashboard/sync-trigger",
        json={"account_number": account_number},
        headers=auth_headers,
    )
    assert trig_resp.status_code == 200
    assert trig_resp.json()["status"] == "SYNC_REQUESTED"

    # Verify telemetry now reflects SYNCING
    tel_resp = await async_client.get(
        f"/api/v1/dashboard/sync-telemetry?account_number={account_number}",
        headers=auth_headers,
    )
    assert tel_resp.status_code == 200
    assert tel_resp.json()["sync_status"] == "SYNCING"


@pytest.mark.asyncio
async def test_manual_sync_trigger_cross_tenant_rejection(async_client: AsyncClient):
    """Test 10: Confirms unauthorized manual sync trigger returns HTTP 404."""
    account_a = 9941001
    auth_headers_a, _, _, _, _, _ = await setup_production_test_environment(async_client, account_a)

    account_b = 9941002
    auth_headers_b, _, _, _, _, _ = await setup_production_test_environment(async_client, account_b)

    # Tenant B tries to trigger sync on Tenant A's account
    resp = await async_client.post(
        "/api/v1/dashboard/sync-trigger",
        json={"account_number": account_a},
        headers=auth_headers_b,
    )
    assert resp.status_code == 404
