import asyncio
import httpx

async def test_handshake():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
        # 1. Login
        login_res = await client.post("/api/v1/auth/login", json={
            "email": "vaibhav251001@gmail.com",
            "password": "TradeDNA@2026"
        })
        print("Login status:", login_res.status_code)
        token = login_res.json()["access_token"]

        # 2. Generate Pairing Token
        pairing_res = await client.post(
            "/api/v1/connections/pair",
            headers={"Authorization": f"Bearer {token}"}
        )
        print("Pairing token status:", pairing_res.status_code)
        print("Pairing token response:", pairing_res.json())
        pairing_token = pairing_res.json()["pairing_token"]
        print("Generated Pairing Token:", pairing_token)

        # 3. Exchange Handshake (as MT5 EA)
        exchange_res = await client.post(
            "/api/v1/exness/connection/exchange",
            json={
                "pairing_token": pairing_token,
                "client_nonce": "test_nonce_12345",
                "broker": "EXNESS",
                "account_number": 267965551,
                "server_name": "Exness-MT5Trial",
                "trade_mode": "DEMO",
                "currency": "USD",
                "terminal_build": 4150,
                "connector_version": "1.0.0"
            }
        )
        print("Exchange status:", exchange_res.status_code)
        print("Exchange response:", exchange_res.json())

if __name__ == "__main__":
    asyncio.run(test_handshake())
