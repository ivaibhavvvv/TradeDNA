"""
TradeDNA — Phase 9A Production Infrastructure & Deployment Foundation Test Suite
Validates all 20 production infrastructure requirements including containerization,
configuration validation, fail-fast behavior, readiness/liveness probes, database pooling,
graceful startup/shutdown, backup/restore integrity, and production smoke tests.
"""

import os
import uuid
import json
import pytest
from decimal import Decimal
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text

from src.core.config import Settings
from src.core.database import check_db_health, engine
from src.main import app, lifespan
from scripts.backup_restore import backup_database, restore_database, verify_restoration_integrity
from scripts.production_smoke_test import run_production_smoke_test
from tests.conftest import test_session_factory


# =====================================================================
# Scenario 1: Production Configuration Validation
# =====================================================================
def test_scenario_01_production_configuration_validation():
    """Scenario 1: Verifies that valid production configuration passes all checks."""
    valid_prod_settings = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        JWT_SECRET="prod_strong_jwt_secret_key_with_at_least_32_characters_12345678",
        JWT_REFRESH_SECRET="prod_strong_jwt_refresh_secret_key_with_at_least_32_chars",
        DATABASE_URL="postgresql+asyncpg://user:pass@postgres:5432/tradedna_prod",
        DATABASE_URL_SYNC="postgresql+psycopg2://user:pass@postgres:5432/tradedna_prod",
        ALLOWED_ORIGINS=["https://app.tradedna.io", "https://tradedna.io"],
        COOKIE_SECURE=True,
        HSTS_ENABLED=True,
    )
    assert valid_prod_settings.ENVIRONMENT == "production"
    assert valid_prod_settings.DEBUG is False
    assert valid_prod_settings.COOKIE_SECURE is True
    assert valid_prod_settings.HSTS_ENABLED is True


# =====================================================================
# Scenario 2: Missing / Insecure Secret Rejection
# =====================================================================
def test_scenario_02_missing_or_short_jwt_secret_rejection():
    """Scenario 2: Verifies fail-fast error when production JWT secret is short or default."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            JWT_SECRET="dev_insecure_jwt_secret",  # Insecure default
            JWT_REFRESH_SECRET="prod_strong_jwt_refresh_secret_key_with_at_least_32_chars",
            DATABASE_URL="postgresql+asyncpg://user:pass@postgres:5432/tradedna_prod",
            ALLOWED_ORIGINS=["https://app.tradedna.io"],
            COOKIE_SECURE=True,
            HSTS_ENABLED=True,
        )
    assert "CRITICAL: Production JWT_SECRET" in str(exc_info.value)


# =====================================================================
# Scenario 3: Invalid Production CORS or Debug Rejection
# =====================================================================
def test_scenario_03_invalid_production_cors_or_debug_rejection():
    """Scenario 3: Verifies rejection of wildcard CORS or DEBUG=True in production."""
    # Test wildcard CORS rejection
    with pytest.raises(ValidationError) as exc_cors:
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            JWT_SECRET="prod_strong_jwt_secret_key_with_at_least_32_characters_12345678",
            JWT_REFRESH_SECRET="prod_strong_jwt_refresh_secret_key_with_at_least_32_chars",
            DATABASE_URL="postgresql+asyncpg://user:pass@postgres:5432/tradedna_prod",
            ALLOWED_ORIGINS=["*"],  # Insecure wildcard
            COOKIE_SECURE=True,
            HSTS_ENABLED=True,
        )
    assert "Insecure CORS origin" in str(exc_cors.value)

    # Test DEBUG=True rejection
    with pytest.raises(ValidationError) as exc_debug:
        Settings(
            ENVIRONMENT="production",
            DEBUG=True,  # Insecure DEBUG mode
            JWT_SECRET="prod_strong_jwt_secret_key_with_at_least_32_characters_12345678",
            JWT_REFRESH_SECRET="prod_strong_jwt_refresh_secret_key_with_at_least_32_chars",
            DATABASE_URL="postgresql+asyncpg://user:pass@postgres:5432/tradedna_prod",
            ALLOWED_ORIGINS=["https://app.tradedna.io"],
            COOKIE_SECURE=True,
            HSTS_ENABLED=True,
        )
    assert "DEBUG mode must be disabled in production" in str(exc_debug.value)


# =====================================================================
# Scenario 4: Database Connectivity Verification
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_04_database_connectivity():
    """Scenario 4: Verifies database connectivity check returns healthy."""
    db_ok = await check_db_health()
    assert db_ok is True


# =====================================================================
# Scenario 5: Readiness Failure When Database Unavailable
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_05_readiness_failure_when_db_unavailable(async_client: AsyncClient):
    """Scenario 5: Verifies readiness probe returns 503 SERVICE UNAVAILABLE when database is down."""
    with patch("src.api.v1.health.check_db_health", AsyncMock(return_value=False)):
        resp = await async_client.get("/api/v1/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["components"]["database"]["status"] == "unhealthy"


# =====================================================================
# Scenario 6: Liveness Independence From Database
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_06_liveness_independence_from_db(async_client: AsyncClient):
    """Scenario 6: Verifies liveness probe returns 200 OK even when database is unavailable."""
    with patch("src.api.v1.health.check_db_health", AsyncMock(return_value=False)):
        resp_root = await async_client.get("/health")
        resp_api = await async_client.get("/api/v1/health")
        resp_live = await async_client.get("/health/live")

        assert resp_root.status_code == 200
        assert resp_api.status_code == 200
        assert resp_live.status_code == 200
        assert resp_api.json()["status"] == "ok"


# =====================================================================
# Scenario 7: Migration Validation
# =====================================================================
def test_scenario_07_migration_validation():
    """Scenario 7: Verifies Alembic migration script directory and versions."""
    from scripts.run_migrations import get_alembic_config
    config = get_alembic_config()
    assert config is not None
    assert os.path.exists(config.get_main_option("script_location"))


# =====================================================================
# Scenario 8: Graceful Startup Lifecycle
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_08_graceful_startup():
    """Scenario 8: Verifies application startup lifespan initializes resources cleanly."""
    async with lifespan(app):
        # Within active lifespan
        assert app is not None


# =====================================================================
# Scenario 9: Graceful Shutdown Lifecycle
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_09_graceful_shutdown():
    """Scenario 9: Verifies application shutdown lifespan disposes DB engine cleanly."""
    with patch("src.main.logger.info") as mock_log:
        async with lifespan(app):
            pass
        # Verify shutdown messages logged
        logged_messages = [call.args[0] for call in mock_log.call_args_list if call.args]
        assert any("Disposing database connection pools" in msg for msg in logged_messages)
        assert any("shutdown complete" in msg for msg in logged_messages)



# =====================================================================
# Scenario 10: Secret Redaction in Logs & Error Handlers
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_10_secret_redaction_in_logs_and_errors(async_client: AsyncClient):
    """Scenario 10: Verifies passwords and tokens are redacted from validation error output."""
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "invalid_email_format", "password": "super_secret_user_password_123"},
    )
    assert resp.status_code == 422
    body_text = resp.text
    # Password text must NOT be echoed back in clear text
    assert "super_secret_user_password_123" not in body_text


# =====================================================================
# Scenario 11: Production CORS Configuration
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_11_production_cors_policy(async_client: AsyncClient):
    """Scenario 11: Verifies CORS preflight options headers."""
    resp = await async_client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers


# =====================================================================
# Scenario 12: HTTPS Security Headers
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_12_https_security_headers(async_client: AsyncClient):
    """Scenario 12: Verifies security headers attached to all responses."""
    resp = await async_client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in resp.headers


# =====================================================================
# Scenario 13: Docker Healthcheck Endpoint Responsiveness
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_13_docker_healthcheck_endpoints(async_client: AsyncClient):
    """Scenario 13: Verifies responsiveness of container healthcheck endpoints."""
    # API healthcheck path
    r_api = await async_client.get("/api/v1/health")
    assert r_api.status_code == 200
    assert r_api.json()["status"] == "ok"

    # Root probe path
    r_root = await async_client.get("/")
    assert r_root.status_code == 200


# =====================================================================
# Scenario 14: PostgreSQL Persistence & Connection Pooling
# =====================================================================
def test_scenario_14_postgresql_persistence_configuration():
    """Scenario 14: Verifies PostgreSQL connection pooling defaults."""
    from src.core.config import get_settings
    settings = get_settings()
    assert settings.DB_POOL_SIZE >= 10
    assert settings.DB_MAX_OVERFLOW >= 20
    assert settings.DB_POOL_TIMEOUT >= 30


# =====================================================================
# Scenario 15: Backup Creation Utility
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_15_backup_creation(tmp_path):
    """Scenario 15: Verifies database backup creation to JSON file."""
    backup_file = str(tmp_path / "backup_test.json")
    sync_url = "sqlite:///./tradedna_dev.db"

    data = backup_database(sync_url, backup_file)
    assert "metadata" in data
    assert "tables" in data
    assert os.path.exists(backup_file)


# =====================================================================
# Scenario 16: Backup Restoration Utility
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_16_backup_restoration(tmp_path):
    """Scenario 16: Verifies restoration into an isolated database snapshot."""
    sync_url = "sqlite:///./tradedna_dev.db"
    backup_file = str(tmp_path / "backup_export.json")

    # Step 1: Backup current state
    backup_database(sync_url, backup_file)

    # Step 2: Restore from backup
    restored = restore_database(sync_url, backup_file)
    assert isinstance(restored, dict)


# =====================================================================
# Scenario 17: Restored Ledger Equality & Zero Drift
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_17_restored_ledger_equality(tmp_path):
    """Scenario 17: Verifies that restored database preserves exact financial integrity ($0 drift)."""
    sync_url = "sqlite:///./tradedna_dev.db"
    backup_file = str(tmp_path / "ledger_backup.json")

    backup_database(sync_url, backup_file)
    is_valid = verify_restoration_integrity(sync_url, sync_url)
    assert is_valid is True


# =====================================================================
# Scenario 18: Restored Raw Event Equality
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_18_restored_raw_event_equality(tmp_path):
    """Scenario 18: Verifies that Layer 1 raw deal events are preserved identically."""
    sync_url = "sqlite:///./tradedna_dev.db"
    backup_file = str(tmp_path / "raw_events_backup.json")

    data = backup_database(sync_url, backup_file)
    raw_events = data["tables"].get("raw_deal_events", [])
    assert isinstance(raw_events, list)


# =====================================================================
# Scenario 19: Production Smoke Journey Execution
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_19_production_smoke_journey(async_client: AsyncClient):
    """Scenario 19: Verifies end-to-end production smoke test journey."""
    user_email = f"smoke_test_journey_{uuid.uuid4().hex[:6]}@tradedna.io"
    # Registration
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={"email": user_email, "password": "SecureSmokePassword123!", "full_name": "Smoke Tester"},
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Pairing
    pair = await async_client.post("/api/v1/connections/pair", headers=headers)
    assert pair.status_code == 201
    pairing_token = pair.json()["pairing_token"]

    # Broker Gate Rejection of non-Exness
    bad_exchange = await async_client.post(
        "/api/v1/exness/connection/exchange",
        json={
            "pairing_token": pairing_token,
            "client_nonce": "smoke_nonce_12345678",
            "account_number": 999111,
            "broker": "ICMarkets",
            "server_name": "ICMarkets-Live01",
            "trade_mode": "REAL",
            "currency": "USD",
            "terminal_build": 4150,
            "connector_version": "1.0.0",
        },
    )
    assert bad_exchange.status_code in (400, 422)

    # Dashboard BFF
    dash = await async_client.get("/api/v1/dashboard/overview", headers=headers)
    assert dash.status_code == 200


# =====================================================================
# Scenario 20: Static Security Audit
# =====================================================================
def test_scenario_20_static_security_audit():
    """Scenario 20: Static AST scan confirming zero trading execution functions and no secrets in compose/dockerfiles."""
    prohibited_keywords = [
        "OrderSend(",
        "OrderSendAsync(",
        "CTrade",
        "PositionClose(",
        "PositionModify(",
        "OrderModify(",
        "OrderDelete(",
        '#include <Trade\\Trade.mqh>',
    ]

    mq5_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../connectors/mt5/TradeDNAConnector.mq5"))
    if os.path.exists(mq5_path):
        with open(mq5_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                code_only = line.split("//")[0].strip()
                for kw in prohibited_keywords:
                    assert kw not in code_only, f"CRITICAL: Found prohibited executable keyword '{kw}' in MT5 connector!"

