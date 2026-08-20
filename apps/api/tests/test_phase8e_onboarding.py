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
from src.core.security import create_access_token, hash_password
from src.models.device import Device
from src.models.onboarding import OnboardingProgress
from src.models.tenant import Tenant
from src.models.user import User
from tests.test_phase8d_e2e_production import build_signed_headers


@pytest.mark.asyncio
async def test_onboarding_state_initialization_on_register(async_client: AsyncClient):
    """Test 1: Verifies that new user registration creates an initial onboarding progress record."""
    email = f"onboarding_trader_{uuid.uuid4().hex[:6]}@example.com"
    reg_resp = await async_client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Alex Trader",
        "tenant_name": "Alex Trading Desk",
    })
    assert reg_resp.status_code == 201
    token = reg_resp.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    state_resp = await async_client.get("/api/v1/onboarding/state", headers=auth_headers)
    assert state_resp.status_code == 200
    state = state_resp.json()

    assert state["current_step"] in ("EMAIL_VERIFICATION_PENDING", "REGISTERED")
    assert state["is_completed"] is False
    assert state["email_verified"] is False
    assert state["default_currency"] == "USD"


@pytest.mark.asyncio
async def test_onboarding_email_verification_valid_and_invalid(async_client: AsyncClient):
    """Test 2: Verifies email code verification with invalid rejection and valid state transition."""
    email = f"verify_trader_{uuid.uuid4().hex[:6]}@example.com"
    reg_resp = await async_client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Jordan Bell",
    })
    token = reg_resp.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 1. Invalid verification code
    invalid_resp = await async_client.post(
        "/api/v1/onboarding/verify-email",
        json={"code": "000000"},
        headers=auth_headers,
    )
    assert invalid_resp.status_code == 400

    # 2. Valid universal verification code
    valid_resp = await async_client.post(
        "/api/v1/onboarding/verify-email",
        json={"code": "789456"},
        headers=auth_headers,
    )
    assert valid_resp.status_code == 200
    state = valid_resp.json()
    assert state["email_verified"] is True
    assert state["current_step"] == "EMAIL_VERIFIED"


@pytest.mark.asyncio
async def test_onboarding_resend_code(async_client: AsyncClient):
    """Test 3: Verifies dispatching of fresh verification code."""
    email = f"resend_{uuid.uuid4().hex[:6]}@example.com"
    reg_resp = await async_client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Taylor Swiftly",
    })
    token = reg_resp.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    resend_resp = await async_client.post("/api/v1/onboarding/resend-code", headers=auth_headers)
    assert resend_resp.status_code == 200
    assert resend_resp.json()["status"] == "SENT"


@pytest.mark.asyncio
async def test_onboarding_workspace_configuration(async_client: AsyncClient):
    """Test 4: Verifies workspace identity customization and step progression."""
    email = f"workspace_{uuid.uuid4().hex[:6]}@example.com"
    reg_resp = await async_client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Morgan Vance",
    })
    token = reg_resp.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Verify email first
    await async_client.post("/api/v1/onboarding/verify-email", json={"code": "789456"}, headers=auth_headers)

    # Configure workspace
    ws_resp = await async_client.post(
        "/api/v1/onboarding/workspace",
        json={
            "workspace_name": "Vance Prop Capital",
            "default_currency": "USD",
            "experience_level": "ADVANCED",
        },
        headers=auth_headers,
    )
    assert ws_resp.status_code == 200
    state = ws_resp.json()
    assert state["current_step"] == "WORKSPACE_CONFIGURED"
    assert state["workspace_name"] == "Vance Prop Capital"


@pytest.mark.asyncio
async def test_onboarding_pairing_initiation(async_client: AsyncClient):
    """Test 5: Verifies single-use pairing token generation scoped to onboarding."""
    email = f"pairing_{uuid.uuid4().hex[:6]}@example.com"
    reg_resp = await async_client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Sam Hill",
    })
    token = reg_resp.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    pair_resp = await async_client.post(
        "/api/v1/onboarding/pair-initiate",
        json={"account_number": 9928801, "server_name": "Exness-Real25"},
        headers=auth_headers,
    )
    assert pair_resp.status_code == 200
    data = pair_resp.json()
    assert len(data["pairing_token"]) >= 32
    assert data["expires_in_seconds"] in (300, 900)
    assert "step_1" in data["instructions"]

    # Verify step progression
    state_resp = await async_client.get("/api/v1/onboarding/state", headers=auth_headers)
    assert state_resp.json()["current_step"] == "AWAITING_CONNECTOR_HANDSHAKE"


@pytest.mark.asyncio
async def test_onboarding_sync_status_lifecycle_and_validation(async_client: AsyncClient):
    """Test 6: Simulates end-to-end connector handshake and historical sync during onboarding."""
    reset_nonce_cache()
    email = f"synclife_{uuid.uuid4().hex[:6]}@example.com"
    reg_resp = await async_client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Chris Paul",
    })
    token = reg_resp.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}
    account_number = 9928802

    # 1. Initiate pairing
    pair_init = await async_client.post(
        "/api/v1/onboarding/pair-initiate",
        json={"account_number": account_number, "server_name": "Exness-Real25"},
        headers=auth_headers,
    )
    pairing_token = pair_init.json()["pairing_token"]

    # Check status before handshake
    status_1 = await async_client.get("/api/v1/onboarding/sync-status", headers=auth_headers)
    assert status_1.json()["status"] == "AWAITING_HANDSHAKE"

    # 2. MT5 EA Handshake Exchange
    handshake_resp = await async_client.post("/api/v1/exness/connection/exchange", json={
        "pairing_token": pairing_token,
        "client_nonce": uuid.uuid4().hex,
        "broker": "EXNESS",
        "account_number": account_number,
        "server_name": "Exness-Real25",
        "trade_mode": "REAL",
        "currency": "USD",
        "terminal_build": 4400,
        "connector_version": "1.0.0",
    })
    assert handshake_resp.status_code == 200
    device_id = handshake_resp.json()["device_id"]
    device_secret = handshake_resp.json()["device_secret"]

    # 3. EA sends account snapshot
    snap_payload = {
        "payload_type": "SNAPSHOT_ACCOUNT",
        "data": {
            "schema_version": "1.0.0",
            "connector_id": str(device_id),
            "account_number": account_number,
            "currency": "USD",
            "balance": "10000.0000",
            "equity": "10250.0000",
            "margin": "150.0000",
            "margin_free": "10100.0000",
            "margin_level": "6833.33",
            "leverage": 500,
            "trade_mode": "REAL",
            "is_hedging": True,
            "snapshot_time": "2026-08-18T22:00:00.000Z",
        },
    }
    raw_snap = json.dumps(snap_payload).encode("utf-8")
    await async_client.post(
        "/api/v1/exness/sync",
        content=raw_snap,
        headers=build_signed_headers(device_id, device_secret, raw_snap),
    )

    # 4. Check sync status post-snapshot
    status_2 = await async_client.get("/api/v1/onboarding/sync-status", headers=auth_headers)
    assert status_2.status_code == 200
    st2_data = status_2.json()
    assert st2_data["account_number"] == account_number
    assert st2_data["currency"] == "USD"
    assert Decimal(str(st2_data["balance"])) == Decimal("10000.0000")
    assert st2_data["is_validated"] is True


@pytest.mark.asyncio
async def test_onboarding_completion_workflow(async_client: AsyncClient):
    """Test 7: Verifies final completion state and redirect target."""
    email = f"complete_{uuid.uuid4().hex[:6]}@example.com"
    reg_resp = await async_client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Devin Booker",
    })
    token = reg_resp.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Complete onboarding
    comp_resp = await async_client.post("/api/v1/onboarding/complete", headers=auth_headers)
    assert comp_resp.status_code == 200
    assert comp_resp.json()["status"] == "COMPLETED"
    assert comp_resp.json()["redirect_url"] == "/dashboard/overview"

    # Verify state reflects completed
    state_resp = await async_client.get("/api/v1/onboarding/state", headers=auth_headers)
    assert state_resp.json()["is_completed"] is True
    assert state_resp.json()["current_step"] == "COMPLETED"


@pytest.mark.asyncio
async def test_onboarding_multi_tenant_isolation(async_client: AsyncClient):
    """Test 8: Strict multi-tenant security barrier—Tenant B cannot access Tenant A onboarding state."""
    # Tenant A
    reg_a = await async_client.post("/api/v1/auth/register", json={
        "email": f"tenant_a_{uuid.uuid4().hex[:6]}@example.com",
        "password": "SecurePassword123!",
        "full_name": "User Alpha",
        "tenant_name": "Alpha Workspace",
    })
    token_a = reg_a.json()["access_token"]
    await async_client.post(
        "/api/v1/onboarding/workspace",
        json={"workspace_name": "Confidential Alpha Desk", "default_currency": "USD"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # Tenant B
    reg_b = await async_client.post("/api/v1/auth/register", json={
        "email": f"tenant_b_{uuid.uuid4().hex[:6]}@example.com",
        "password": "SecurePassword123!",
        "full_name": "User Beta",
        "tenant_name": "Beta Workspace",
    })
    token_b = reg_b.json()["access_token"]

    # Query state as Tenant B
    state_b_resp = await async_client.get(
        "/api/v1/onboarding/state",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    state_b = state_b_resp.json()

    assert state_b["tenant_id"] != reg_a.json()["user"]["tenant_id"]
    assert state_b["workspace_name"] != "Confidential Alpha Desk"
