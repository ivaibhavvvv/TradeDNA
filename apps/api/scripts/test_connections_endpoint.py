import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from sqlalchemy import select
from src.core.database import async_session_factory
from src.core.security import create_access_token
from src.models.user import User

async def main():
    async with async_session_factory() as session:
        user_stmt = select(User).where(User.email == "vaibhav251001@gmail.com")
        res = await session.execute(user_stmt)
        user = res.scalar_one_or_none()
        if not user:
            print("User not found")
            return

        token = create_access_token(
            subject=str(user.id),
            tenant_id=str(user.tenant_id),
        )
        headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000/api/v1") as client:
        # Test connections
        conn_res = await client.get("/connections", headers=headers)
        print("Connections status:", conn_res.status_code)
        if conn_res.status_code == 200:
            data = conn_res.json()
            print("Connections accounts:", len(data["accounts"]))
            print("Connections total_accounts:", data["total_accounts"])
            print("Connections online_devices:", data["online_devices"])

        # Test dashboard overview
        dash_res = await client.get("/dashboard/overview", headers=headers)
        print("Dashboard overview status:", dash_res.status_code)
        if dash_res.status_code == 200:
            print("Dashboard has_account:", dash_res.json().get("has_account"))

        # Test performance
        perf_res = await client.get("/dashboard/performance", headers=headers)
        print("Performance status:", perf_res.status_code)
        if perf_res.status_code == 200:
            print("Performance has_data:", perf_res.json().get("has_data"))

if __name__ == "__main__":
    asyncio.run(main())
