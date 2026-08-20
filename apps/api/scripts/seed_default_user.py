import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from src.core.database import async_session_factory
from src.core.security import hash_password
from src.models.user import User
from src.models.tenant import Tenant

async def seed_user():
    async with async_session_factory() as db:
        stmt = select(User).where(User.email == "vaibhav251001@gmail.com")
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        if not user:
            tenant = Tenant(name="Vaibhav Chauhan's Workspace")
            db.add(tenant)
            await db.flush()

            user = User(
                tenant_id=tenant.id,
                email="vaibhav251001@gmail.com",
                password_hash=hash_password("TradeDNA@2026"),
                full_name="Vaibhav Chauhan",
                is_active=True,
                is_verified=True,
            )
            db.add(user)
            await db.commit()
            print("Default user created: vaibhav251001@gmail.com / TradeDNA@2026")
        else:
            user.password_hash = hash_password("TradeDNA@2026")
            user.is_active = True
            await db.commit()
            print("Default user password updated: vaibhav251001@gmail.com / TradeDNA@2026")

if __name__ == "__main__":
    asyncio.run(seed_user())
