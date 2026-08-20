import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_session_logout(async_client: AsyncClient):
    # 1. Register
    reg_payload = {
        "email": "logout_test@example.com",
        "password": "ValidPassword123!",
        "full_name": "Logout Test User",
    }
    reg_res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Verify /me works
    me_res1 = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_res1.status_code == 200

    # 3. Logout
    logout_res = await async_client.post("/api/v1/auth/logout", headers=headers)
    assert logout_res.status_code == 200
    assert logout_res.json()["success"] is True

    # 4. Verify /me is now rejected (401 Unauthorized)
    me_res2 = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_res2.status_code == 401
    assert "terminated or revoked" in me_res2.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_logout_all_sessions(async_client: AsyncClient):
    # 1. Register (Device 1)
    reg_payload = {
        "email": "logout_all_test@example.com",
        "password": "ValidPassword123!",
        "full_name": "Logout All User",
    }
    reg_res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    token_device1 = reg_res.json()["access_token"]

    # 2. Login from Device 2
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "logout_all_test@example.com", "password": "ValidPassword123!"},
    )
    token_device2 = login_res.json()["access_token"]

    # Verify both tokens work
    assert (await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_device1}"})).status_code == 200
    assert (await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_device2}"})).status_code == 200

    # 3. Logout All from Device 2
    logout_all_res = await async_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {token_device2}"},
    )
    assert logout_all_res.status_code == 200

    # 4. Prove BOTH device sessions are now terminated!
    assert (await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_device1}"})).status_code == 401
    assert (await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_device2}"})).status_code == 401


@pytest.mark.asyncio
async def test_list_user_sessions(async_client: AsyncClient):
    reg_payload = {
        "email": "sessions_user@example.com",
        "password": "ValidPassword123!",
        "full_name": "Sessions User",
    }
    reg_res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    token = reg_res.json()["access_token"]

    res = await async_client.get("/api/v1/auth/sessions", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    sessions = res.json()
    assert len(sessions) == 1
    assert sessions[0]["is_current"] is True
    assert sessions[0]["is_revoked"] is False
