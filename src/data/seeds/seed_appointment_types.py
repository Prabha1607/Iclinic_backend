from sqlalchemy import text
from src.data.clients.postgres_client import AsyncSessionLocal


async def seed_appointment_types():
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
            INSERT INTO appointment_types
            (id, name, description, duration_minutes, instructions)
            VALUES
            (1,'general_checkup',
            'Routine visit for fever, cold, tiredness, or any general health concern',
            30,
            'Please come 10 minutes early'),

            (2,'cardiologist',
            'Heart-related issues like chest pain, fast heartbeat, or high blood pressure',
            30,
            'Bring previous ECG reports'),

            (3,'pediatric',
            'Health care for babies, children, and teenagers',
            30,
            'Bring vaccination records')
            ON CONFLICT (id) DO NOTHING;
            """)
        )

        await session.commit()


        