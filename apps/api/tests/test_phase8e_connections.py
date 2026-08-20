from datetime import datetime, timezone
from decimal import Decimal
import json
import time
from typing import Any, Dict
import uuid
import httpx
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from src.core.connector_auth import reset_nonce_cache
from src.core.security import create_access_token
from src.models.device import Device
from src.models.sync_state import AccountSyncState
from tests.test_phase8d_e2e_production import build_signed_headers, setup_production_test_environment


@pytest.mark.asyncio
async def test_connections_overview_and_device_listing(async_client: AsyncClient):
    """Test 1: Verifies Connection Center overview aggregations, masked accounts, and safe device DTOs."""
    account_number = 9930101
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number, server_name="Exness-Real25", currency="USD"
    )

    resp = await async_client.get("/api/v1/connections", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_accounts"] >= 1
    assert data["total_devices"] >= 1
    assert data["online_devices"] >= 1

    acc = next(a for a in data["accounts"] if a["account_number"] == account_number)
    assert acc["masked_account_number"].startswith("993")
    assert acc["masked_account_number"].endswith("01")
    assert acc["server_name"] == "Exness-Real25"
    assert acc["currency"] == "USD"
    assert acc["connection_status"] in ("CONNECTED", "SYNCING")
    assert len(acc["devices"]) >= 1

    dev = acc["devices"][0]
    assert dev["masked_device_id"].startswith("dev_")
    assert dev["is_active"] is True
    assert dev["is_revoked"] is False

    # Verify secret non-exposure
    resp_text = json.dumps(data)
    assert device_secret not in resp_text
    assert "device_secret_hash" not in resp_text


@pytest.mark.asyncio
async def test_account_detail_query(async_client: AsyncClient):
    """Test 2: Verifies single account detailed connection telemetry."""
    account_number = 9930201
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    resp = await async_client.get(f"/api/v1/connections/{account_number}", headers=auth_headers)
    assert resp.status_code == 200
    acc = resp.json()
    assert acc["account_number"] == account_number
    assert acc["server_name"] == "Exness-Real25"
    assert acc["devices_count"] >= 1


@pytest.mark.asyncio
async def test_cross_tenant_isolation_on_account_query(async_client: AsyncClient):
    """Test 3: Confirms cross-tenant query for account returns HTTP 404 (zero leakage)."""
    account_number_a = 9930301
    auth_headers_a, dev_a, sec_a, ten_a, user_a, _ = await setup_production_test_environment(
        async_client, account_number_a
    )

    account_number_b = 9930302
    auth_headers_b, dev_b, sec_b, ten_b, user_b, _ = await setup_production_test_environment(
        async_client, account_number_b
    )

    # Tenant B queries Tenant A's account
    resp = await async_client.get(f"/api/v1/connections/{account_number_a}", headers=auth_headers_b)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_secure_pairing_token_initiation(async_client: AsyncClient):
    """Test 4: Initiates pairing token via connections router."""
    account_number = 9930401
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    resp = await async_client.post("/api/v1/connections/pair", headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["pairing_token"]) >= 32
    assert data["expires_in_seconds"] in (300, 900)


@pytest.mark.asyncio
async def test_device_revocation_and_ingress_cutoff(async_client: AsyncClient):
    """Test 5: Revokes device and verifies immediate ingress cutoff."""
    reset_nonce_cache()
    account_number = 9930501
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    # Revoke device
    revoke_resp = await async_client.post(
        f"/api/v1/connections/devices/{device_id}/revoke",
        headers=auth_headers,
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["status"] == "REVOKED"

    # Attempt heartbeat sync with revoked device
    hb_payload = {
        "payload_type": "HEARTBEAT",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": account_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    raw_hb = json.dumps(hb_payload).encode("utf-8")
    sync_resp = await async_client.post(
        "/api/v1/exness/sync",
        content=raw_hb,
        headers=build_signed_headers(device_id, device_secret, raw_hb),
    )
    assert sync_resp.status_code == 401


@pytest.mark.asyncio
async def test_revoke_all_devices_for_account(async_client: AsyncClient):
    """Test 6: Revokes all devices associated with an account."""
    account_number = 9930601
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    revoke_resp = await async_client.post(
        f"/api/v1/connections/accounts/{account_number}/revoke-all",
        headers=auth_headers,
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["devices_revoked_count"] >= 1


@pytest.mark.asyncio
async def test_update_account_display_name(async_client: AsyncClient):
    """Test 7: Customizes local display label for an authorized account."""
    account_number = 9930701
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    patch_resp = await async_client.patch(
        f"/api/v1/connections/accounts/{account_number}/display-name",
        json={"display_name": "Primary Live Scalper"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["display_name"] == "Primary Live Scalper"

    # Confirm updated in overview
    ov_resp = await async_client.get("/api/v1/connections", headers=auth_headers)
    acc = next(a for a in ov_resp.json()["accounts"] if a["account_number"] == account_number)
    assert acc["display_name"] == "Primary Live Scalper"


@pytest.mark.asyncio
async def test_soft_delete_account_view(async_client: AsyncClient):
    """Test 8: Soft-hides account from view without mutating historical financial truth."""
    account_number = 9930801
    auth_headers, device_id, device_secret, tenant_id, user_id, acc_num = await setup_production_test_environment(
        async_client, account_number
    )

    del_resp = await async_client.delete(f"/api/v1/connections/accounts/{account_number}", headers=auth_headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "HIDDEN"

    # Verify no longer in active overview
    ov_resp = await async_client.get("/api/v1/connections", headers=auth_headers)
    account_nums = [a["account_number"] for a in ov_resp.json()["accounts"]]
    assert account_number not in account_nums
