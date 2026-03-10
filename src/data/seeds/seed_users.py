from sqlalchemy import text
from src.data.clients.postgres_client import AsyncSessionLocal
from src.config.hashing import get_password_hash


async def seed_users():
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text("""
                SELECT setval('users_id_seq', COALESCE((SELECT MAX(id) FROM users), 1));
            """))

            hashed_password = get_password_hash("Dhars@012")

            query = text("""
                INSERT INTO users (
                    first_name,
                    last_name,
                    country_code,
                    phone_no,
                    email,
                    password,
                    is_active,
                    role_id,
                    created_at,
                    updated_at
                )
                VALUES (
                    'Dharshini',
                    'K',
                    '+91',
                    '9025824515',
                    'dharsveni@gmail.com',
                    :password,
                    true,
                    3,
                    NOW(),
                    NOW()
                )
                ON CONFLICT (phone_no) DO NOTHING;
            """)

            await session.execute(query, {"password": hashed_password})

            await session.commit()

        except Exception as e:
            await session.rollback()
            print("Error seeding user Dharshini:", e)

