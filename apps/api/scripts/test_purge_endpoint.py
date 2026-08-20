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
        # Check initial accounts
        conn_res = await client.get("/connections", headers=headers)
        initial_accounts = [a["account_number"] for a in conn_res.json()["accounts"]]
        print("Initial accounts:", initial_accounts)

        # Test purge for account 434120065 if present
        if 434120065 in initial_accounts:
            print("Purging account 434120065...")
            purge_res = await client.delete("/connections/accounts/434120065/purge", headers=headers)
            print("Purge response status:", purge_res.status_code)
            print("Purge response body:", purge_res.text)

            # Re-check connections
            recheck_res = await client.get("/connections", headers=headers)
            print("Accounts after purge:", [a["account_number"] for a in recheck_res.json()["accounts"]])

if __name__ == "__main__":
    asyncio.run(main())
