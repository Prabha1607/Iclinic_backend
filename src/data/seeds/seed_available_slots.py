from sqlalchemy import text
from src.data.clients.postgres_client import AsyncSessionLocal

async def seed_available_slots():
    async with AsyncSessionLocal() as session:
        await session.execute(
    text("""
    INSERT INTO available_slots
    (provider_id, availability_date, start_time, end_time, notes)
    VALUES
    -- Dr. Arjun Kumar
    (1, '2026-03-09', '09:00', '09:30', 'Morning slot'),
    (1, '2026-03-09', '09:30', '10:00', 'Morning slot'),
    (1, '2026-03-09', '10:00', '10:30', 'Morning slot'),
    (1, '2026-03-10', '09:00', '09:30', 'Morning slot'),
    (1, '2026-03-10', '09:30', '10:00', 'Morning slot'),
    (1, '2026-03-10', '14:00', '14:30', 'Afternoon slot'),
    (1, '2026-03-10', '14:30', '15:00', 'Afternoon slot'),
    (1, '2026-03-11', '10:00', '10:30', 'Morning slot'),
    (1, '2026-03-11', '10:30', '11:00', 'Morning slot'),

    -- Dr. Meena Ravi
    (2, '2026-03-11', '16:00', '16:30', 'Evening slot'),
    (2, '2026-03-11', '16:30', '17:00', 'Evening slot'),
    (2, '2026-03-10', '10:00', '10:30', 'Heart checkup'),
    (2, '2026-03-10', '10:30', '11:00', 'Heart checkup'),
    (2, '2026-03-12', '11:00', '11:30', 'Heart checkup'),
    (2, '2026-03-12', '11:30', '12:00', 'Heart checkup'),

    -- Dr. Rahul Sharma
    (3, '2026-03-11', '15:00', '15:30', 'Vaccination slot'),
    (3, '2026-03-11', '15:30', '16:00', 'Vaccination slot'),
    (3, '2026-03-12', '09:00', '09:30', 'Kids clinic'),
    (3, '2026-03-12', '09:30', '10:00', 'Kids clinic'),
    (3, '2026-03-12', '11:00', '11:30', 'Kids checkup'),
    (3, '2026-03-12', '11:30', '12:00', 'Kids checkup')
    
    ON CONFLICT (provider_id, availability_date, start_time, end_time) DO NOTHING;
    """)
)

        await session.commit()

