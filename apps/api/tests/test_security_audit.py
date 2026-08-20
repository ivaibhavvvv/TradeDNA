import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.audit import AuditLog


@pytest.mark.asyncio
async def test_audit_logs_created_and_redacted(async_client: AsyncClient, setup_test_database):
    # 1. Register User
    raw_password = "SuperSecretPassword123!"
    reg_payload = {
        "email": "audit_test@example.com",
        "password": raw_password,
        "full_name": "Audit User",
    }
    await async_client.post("/api/v1/auth/register", json=reg_payload)

    # 2. Login User
    await async_client.post(
        "/api/v1/auth/login",
        json={"email": "audit_test@example.com", "password": raw_password},
    )

    # 3. Failed Login Attempt
    await async_client.post(
        "/api/v1/auth/login",
        json={"email": "audit_test@example.com", "password": "WrongPassword!"},
    )
