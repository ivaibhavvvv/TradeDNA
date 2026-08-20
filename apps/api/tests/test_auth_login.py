import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_user_login_success(async_client: AsyncClient):
    # Register first
    reg_payload = {
        "email": "login_test@example.com",
        "password": "ValidPassword123!",
        "full_name": "Login Test User",
    }
    await async_client.post("/api/v1/auth/register", json=reg_payload)

    # Login
    login_payload = {
        "email": "login_test@example.com",
        "password": "ValidPassword123!",
    }
    res = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "login_test@example.com"


@pytest.mark.asyncio
async def test_login_invalid_password_fails(async_client: AsyncClient):
    reg_payload = {
        "email": "wrong_pwd@example.com",
        "password": "ValidPassword123!",
        "full_name": "Password User",
    }
    await async_client.post("/api/v1/auth/register", json=reg_payload)

    login_payload = {
        "email": "wrong_pwd@example.com",
        "password": "WrongPassword999!",
    }
    res = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert res.status_code == 401
    data = res.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert "invalid email or password" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_login_nonexistent_user_fails(async_client: AsyncClient):
    login_payload = {
        "email": "nonexistent@example.com",
        "password": "AnyPassword123!",
    }
    res = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert res.status_code == 401
    data = res.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert "invalid email or password" in data["error"]["message"].lower()
