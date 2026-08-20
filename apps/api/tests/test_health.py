import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_endpoint(async_client: AsyncClient):
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "tradedna-api"
    assert "version" in data
    assert data["tagline"] == "Decode Your Trading."


@pytest.mark.asyncio
async def test_health_liveness_endpoint(async_client: AsyncClient):
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "tradedna-api"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_endpoint(async_client: AsyncClient):
    response = await async_client.get("/api/v1/ready")
    assert response.status_code in [200, 503]
    data = response.json()
    assert "status" in data
    assert "components" in data
    assert "database" in data["components"]


@pytest.mark.asyncio
async def test_request_id_middleware(async_client: AsyncClient):
    response = await async_client.get("/api/v1/health", headers={"X-Request-ID": "custom-req-id-12345"})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "custom-req-id-12345"
