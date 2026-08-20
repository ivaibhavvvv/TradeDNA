import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_user_registration_success(async_client: AsyncClient):
    payload = {
        "email": "trader1@example.com",
        "password": "SecurePassword123!",
        "full_name": "Alex Mercer",
        "tenant_name": "Mercer Trading Org",
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "trader1@example.com"
    assert data["user"]["full_name"] == "Alex Mercer"
    assert "password" not in data["user"]
    assert "password_hash" not in data["user"]
    assert data["user"]["is_active"] is True


@pytest.mark.asyncio
async def test_duplicate_registration_fails(async_client: AsyncClient):
    payload = {
        "email": "dup@example.com",
        "password": "SecurePassword123!",
        "full_name": "Duplicate Trader",
    }
    res1 = await async_client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = await async_client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 422
    err = res2.json()
    assert err["success"] is False
    assert "already exists" in err["error"]["message"].lower()


@pytest.mark.asyncio
async def test_registration_validation_short_password(async_client: AsyncClient):
    payload = {
        "email": "short@example.com",
        "password": "123",
        "full_name": "Short Pwd",
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "VALIDATION_ERROR"
