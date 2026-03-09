from sqlalchemy import text
from src.data.clients.postgres_client import AsyncSessionLocal


async def seed_roles():
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
            INSERT INTO roles (id, role_name)
            VALUES (1, 'patient')
            ON CONFLICT (id) DO NOTHING;
            """)
        )

        await session.execute(
            text("""
            INSERT INTO roles (id, role_name)
            VALUES (2, 'doctor')
            ON CONFLICT (id) DO NOTHING;
            """)
        )

        await session.execute(
            text("""
            INSERT INTO roles (id, role_name)
            VALUES (3, 'front desk assistant')
            ON CONFLICT (id) DO NOTHING;
            """)
        )

        await session.commit()

        