import uuid
from datetime import timedelta
import pytest
from httpx import AsyncClient
from src.core.config import get_settings
from src.core.dependencies import enforce_tenant_isolation
from src.core.exceptions import ForbiddenException
from src.core.security import create_access_token
from src.models.user import User

settings = get_settings()


@pytest.mark.asyncio
async def test_missing_token_rejected(async_client: AsyncClient):
    response = await async_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_invalid_token_rejected(async_client: AsyncClient):
    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid_garbage_token_12345"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_expired_token_rejected(async_client: AsyncClient):
    # Generate expired token
    expired_token = create_access_token(
        subject=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        expires_delta=timedelta(seconds=-60),
    )
    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert "expired" in response.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_tenant_isolation_boundary_enforcement():
    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()

    user_a = User(
        id=uuid.uuid4(),
        tenant_id=tenant_a_id,
        email="user_a@example.com",
        password_hash="fakehash",
        full_name="User A",
    )

    # 1. Accessing own tenant resource succeeds
    enforce_tenant_isolation(resource_tenant_id=tenant_a_id, current_user=user_a)

    # 2. Accessing foreign tenant resource throws ForbiddenException
    with pytest.raises(ForbiddenException) as exc_info:
        enforce_tenant_isolation(resource_tenant_id=tenant_b_id, current_user=user_a)
    assert "cross-tenant" in str(exc_info.value.message).lower()


@pytest.mark.asyncio
async def test_forged_claims_cannot_access_real_tenant(async_client: AsyncClient):
    # Attacker crafts a token with a randomly forged subject UUID
    forged_user_id = str(uuid.uuid4())
    forged_tenant_id = str(uuid.uuid4())
    forged_token = create_access_token(
        subject=forged_user_id,
        tenant_id=forged_tenant_id,
    )

    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {forged_token}"},
    )
    assert response.status_code == 401
    assert "does not exist" in response.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_auth_failure_does_not_leak_stack_traces(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@test.com", "password": "SecretPassword123!"},
    )
    assert response.status_code == 401
    data = response.json()
    assert "traceback" not in data
    assert "stack" not in data
    assert "SecretPassword123!" not in str(data)
    assert data["error"]["code"] == "UNAUTHORIZED"
