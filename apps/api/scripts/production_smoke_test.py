#!/usr/bin/env python3
"""
TradeDNA Automated Production Smoke Test
Executes a strictly read-only verification of all core production capabilities
including liveness, readiness, authentication, pairing, broker gating, and dashboard BFF.
"""

import sys
import uuid
import asyncio
import logging
from httpx import AsyncClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("smoke_test")


async def run_production_smoke_test(base_url: str = "http://localhost:8000") -> bool:
    """Executes the full production smoke test sequence."""
    logger.info(f"Starting Production Smoke Test against target: {base_url}")
    async with AsyncClient(base_url=base_url, timeout=10.0) as client:
        # Step 1: Liveness Probes
        logger.info("Step 1: Checking API liveness endpoints...")
        r1 = await client.get("/health")
        r2 = await client.get("/api/v1/health")
        if r1.status_code != 200 or r2.status_code != 200:
            logger.error(f"Liveness failed: /health={r1.status_code}, /api/v1/health={r2.status_code}")
            return False
        logger.info("  ✓ Liveness probe verified.")

        # Step 2: Readiness Probes
        logger.info("Step 2: Checking API readiness endpoints...")
        r_ready = await client.get("/api/v1/ready")
        if r_ready.status_code not in (200, 503):
            logger.error(f"Readiness probe returned unexpected status: {r_ready.status_code}")
            return False
        logger.info(f"  ✓ Readiness probe responded with status {r_ready.status_code} ({r_ready.json().get('status')}).")

        # Step 3: User Authentication & JWT Issuance
        logger.info("Step 3: Testing User Registration & JWT Authentication...")
        user_email = f"smoke_user_{uuid.uuid4().hex[:6]}@tradedna.io"
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={"email": user_email, "password": "SecureSmokePassword123!", "full_name": "Smoke Test Runner"},
        )
        if reg_resp.status_code != 201:
            logger.error(f"Registration failed: {reg_resp.status_code} {reg_resp.text}")
            return False
        token = reg_resp.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        logger.info("  ✓ Registration & JWT token issuance verified.")

        # Step 4: Pairing Token Generation
        logger.info("Step 4: Testing Secure Exness Pairing Token Generation...")
        pair_resp = await client.post("/api/v1/connections/pair", headers=auth_headers)
        if pair_resp.status_code != 201:
            logger.error(f"Pairing token generation failed: {pair_resp.status_code}")
            return False
        pdata = pair_resp.json()
        raw_pairing_token = pdata["pairing_token"]
        logger.info(f"  ✓ Pairing token generated: length={len(raw_pairing_token)}, expires_in={pdata.get('expires_in_seconds')}s.")

        # Step 5: Exness-Only Broker Gate
        logger.info("Step 5: Testing Exness-Only Broker Gate (Rejection of Non-Exness Broker)...")
        bad_exchange = await client.post(
            "/api/v1/exness/connection/exchange",
            json={
                "pairing_token": raw_pairing_token,
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
        if bad_exchange.status_code not in (400, 422):
            logger.error(f"Broker gate failed to reject non-Exness broker: {bad_exchange.status_code}")
            return False
        logger.info("  ✓ Broker gate successfully rejected non-Exness broker.")

        # Step 6: Dashboard BFF Overview
        logger.info("Step 6: Testing Dashboard BFF Overview...")
        dash_resp = await client.get("/api/v1/dashboard/overview", headers=auth_headers)
        if dash_resp.status_code != 200:
            logger.error(f"Dashboard overview query failed: {dash_resp.status_code}")
            return False
        dash_data = dash_resp.json()
        logger.info(f"  ✓ Dashboard overview loaded: has_account={dash_data.get('has_account')}.")

        # Step 7: Strict Read-Only Verification
        logger.info("Step 7: Verifying Strict Read-Only Invariant (0 Trade Execution Endpoints)...")
        prohibited_routes = ["/api/v1/orders", "/api/v1/trade", "/api/v1/execute", "/api/v1/positions/close"]
        for p_route in prohibited_routes:
            res = await client.post(p_route, headers=auth_headers, json={})
            if res.status_code != 404:
                logger.error(f"CRITICAL: Prohibited route {p_route} responded with {res.status_code}!")
                return False
        logger.info("  ✓ Read-only invariant confirmed: all execution routes returned 404.")

    logger.info("==================================================")
    logger.info("PRODUCTION SMOKE TEST: ALL 7 STEPS PASSED (100%)")
    logger.info("==================================================")
    return True


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    success = asyncio.run(run_production_smoke_test(url))
    sys.exit(0 if success else 1)
