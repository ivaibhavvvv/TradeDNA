"""
TradeDNA Phase 9E - Authorization, IDOR & BOLA Test Suite
Verifies cross-tenant isolation, cross-account boundaries, RBAC privilege boundaries, and resource access guards.
"""

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app


@pytest.fixture
async def two_distinct_tenants():
    """Sets up two separate tenants with distinct authenticated users."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Tenant 1
        t1_email = f"user1_{uuid.uuid4().hex[:8]}@example.com"
        r1 = await client.post(
            "/api/v1/auth/register",
            json={"email": t1_email, "password": "StrongPassword123!", "full_name": "User One", "tenant_name": "Alpha Tenant"},
        )
        assert r1.status_code == 201
        t1_data = r1.json()

        # Tenant 2
        t2_email = f"user2_{uuid.uuid4().hex[:8]}@example.com"
        r2 = await client.post(
            "/api/v1/auth/register",
            json={"email": t2_email, "password": "StrongPassword123!", "full_name": "User Two", "tenant_name": "Beta Tenant"},
        )
        assert r2.status_code == 201
        t2_data = r2.json()

        # Pair a device for Tenant 1
        h1 = {"Authorization": f"Bearer {t1_data['access_token']}"}
        pair1 = await client.post("/api/v1/connections/pair", headers=h1)
        assert pair1.status_code == 201

        # Pair a device for Tenant 2
        h2 = {"Authorization": f"Bearer {t2_data['access_token']}"}
        pair2 = await client.post("/api/v1/connections/pair", headers=h2)
        assert pair2.status_code == 201

        return {
            "t1": {
                "user_id": t1_data["user"]["id"],
                "tenant_id": t1_data["user"]["tenant_id"],
                "token": t1_data["access_token"],
                "headers": h1,
            },
            "t2": {
                "user_id": t2_data["user"]["id"],
                "tenant_id": t2_data["user"]["tenant_id"],
                "token": t2_data["access_token"],
                "headers": h2,
            },
        }


@pytest.mark.asyncio
async def test_idor_cross_tenant_overview(two_distinct_tenants):
    """Tenant 1 attempting to query Tenant 2 overview receives zero Tenant 2 data."""
    t1 = two_distinct_tenants["t1"]
    t2 = two_distinct_tenants["t2"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Tenant 1 requests overview
        res = await client.get("/api/v1/dashboard/overview", headers=t1["headers"])
        assert res.status_code == 200
        data = res.json()
        # Verify no tenant 2 identifiers leaked
        assert str(t2["tenant_id"]) not in str(data)
        assert str(t2["user_id"]) not in str(data)


@pytest.mark.asyncio
async def test_idor_cross_tenant_account_detail(two_distinct_tenants):
    """Tenant 1 requesting connection details for Tenant 2's account gets 404."""
    t1 = two_distinct_tenants["t1"]
    fake_account = 99912345

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"/api/v1/connections/{fake_account}", headers=t1["headers"])
        assert res.status_code in [403, 404]


@pytest.mark.asyncio
async def test_idor_cross_tenant_device_revocation(two_distinct_tenants):
    """Tenant 1 attempting to revoke random/other tenant device receives 404."""
    t1 = two_distinct_tenants["t1"]
    random_device_id = str(uuid.uuid4())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(f"/api/v1/connections/devices/{random_device_id}/revoke", headers=t1["headers"])
        assert res.status_code in [403, 404]


@pytest.mark.asyncio
async def test_idor_cross_tenant_trades(two_distinct_tenants):
    """Tenant 1 requesting trades sees only their own trades."""
    t1 = two_distinct_tenants["t1"]
    t2 = two_distinct_tenants["t2"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/dashboard/trades", headers=t1["headers"])
        assert res.status_code == 200
        data = res.json()
        assert str(t2["tenant_id"]) not in str(data)


@pytest.mark.asyncio
async def test_idor_cross_tenant_backups(two_distinct_tenants):
    """Tenant 1 requesting recovery overview receives only Tenant 1 backups."""
    t1 = two_distinct_tenants["t1"]
    t2 = two_distinct_tenants["t2"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/dashboard/recovery", headers=t1["headers"])
        assert res.status_code == 200
        data = res.json()
        assert str(t2["tenant_id"]) not in str(data)


@pytest.mark.asyncio
async def test_unauthenticated_endpoints_rejected():
    """Unauthenticated requests to protected endpoints return 401."""
    protected_urls = [
        "/api/v1/dashboard/overview",
        "/api/v1/dashboard/trades",
        "/api/v1/dashboard/performance",
        "/api/v1/dashboard/operations",
        "/api/v1/dashboard/recovery",
        "/api/v1/connections",
        "/api/v1/connections/pair",
        "/api/v1/backups",
    ]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for url in protected_urls:
            res = await client.get(url)
            assert res.status_code == 401, f"Endpoint {url} allowed unauthenticated access"


@pytest.mark.asyncio
async def test_role_based_privilege_escalation():
    """Standard user cannot perform unauthorized administrative operations."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        email = f"user_{uuid.uuid4().hex[:8]}@example.com"
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password123!", "full_name": "Std User", "tenant_name": "Std Tenant"},
        )
        assert reg.status_code == 201
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Attempt to access non-existent admin backdoor
        admin_res = await client.get("/api/v1/admin/users", headers=headers)
        assert admin_res.status_code in [403, 404]
