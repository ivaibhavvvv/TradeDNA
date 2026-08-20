import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_refresh_token_rotation_success(async_client: AsyncClient):
    # 1. Register
    reg_payload = {
        "email": "refresh_user@example.com",
        "password": "ValidPassword123!",
        "full_name": "Refresh User",
    }
    reg_res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    token_data1 = reg_res.json()
    refresh_token_v1 = token_data1["refresh_token"]

    # 2. Perform Refresh Rotation
    refresh_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token_v1},
    )
    assert refresh_res.status_code == 200
    token_data2 = refresh_res.json()
    refresh_token_v2 = token_data2["refresh_token"]

    # Verify a new token was issued
    assert refresh_token_v2 != refresh_token_v1
    assert "access_token" in token_data2


@pytest.mark.asyncio
async def test_refresh_token_reuse_detection_revokes_session(async_client: AsyncClient):
    # 1. Register
    reg_payload = {
        "email": "reuse_victim@example.com",
        "password": "ValidPassword123!",
        "full_name": "Reuse Victim",
    }
    reg_res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    refresh_token_v1 = reg_res.json()["refresh_token"]

    # 2. Legitimate refresh (v1 -> v2)
    refresh_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token_v1},
    )
    assert refresh_res.status_code == 200
    access_token_v2 = refresh_res.json()["access_token"]
    refresh_token_v2 = refresh_res.json()["refresh_token"]

    # 3. Attacker presents REPLAYED refresh_token_v1 (TOKEN REUSE ATTACK)
    attack_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token_v1},
    )
    assert attack_res.status_code == 401
    assert "reuse detected" in attack_res.json()["error"]["message"].lower()

    # 4. Prove the session has been terminated: legitimate v2 token now fails!
    reuse_v2_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token_v2},
    )
    assert reuse_v2_res.status_code == 401

    # 5. Access token from this session is also rejected on protected endpoint
    me_res = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token_v2}"},
    )
    assert me_res.status_code == 401
    assert "terminated or revoked" in me_res.json()["error"]["message"].lower()
