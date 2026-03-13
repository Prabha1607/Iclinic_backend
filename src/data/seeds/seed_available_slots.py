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
    (1, '2026-03-13', '09:00', '09:30', 'Morning slot'),
    (1, '2026-03-13', '09:30', '10:00', 'Morning slot'),
    (1, '2026-03-13', '14:00', '14:30', 'Afternoon slot'),
    (1, '2026-03-13', '14:30', '15:00', 'Afternoon slot'),
    (1, '2026-03-14', '09:00', '09:30', 'Morning slot'),
    (1, '2026-03-14', '09:30', '10:00', 'Morning slot'),
    (1, '2026-03-14', '10:00', '10:30', 'Morning slot'),
    (1, '2026-03-14', '14:00', '14:30', 'Afternoon slot'),
    (1, '2026-03-15', '10:00', '10:30', 'Morning slot'),
    (1, '2026-03-15', '10:30', '11:00', 'Morning slot'),
    (1, '2026-03-15', '14:00', '14:30', 'Afternoon slot'),
    (1, '2026-03-15', '14:30', '15:00', 'Afternoon slot'),

    -- Dr. Meena Ravi
    (2, '2026-03-11', '16:00', '16:30', 'Evening slot'),
    (2, '2026-03-11', '16:30', '17:00', 'Evening slot'),
    (2, '2026-03-10', '10:00', '10:30', 'Heart checkup'),
    (2, '2026-03-10', '10:30', '11:00', 'Heart checkup'),
    (2, '2026-03-12', '11:00', '11:30', 'Heart checkup'),
    (2, '2026-03-12', '11:30', '12:00', 'Heart checkup'),
    (2, '2026-03-13', '10:00', '10:30', 'Heart checkup'),
    (2, '2026-03-13', '10:30', '11:00', 'Heart checkup'),
    (2, '2026-03-13', '16:00', '16:30', 'Evening slot'),
    (2, '2026-03-14', '11:00', '11:30', 'Heart checkup'),
    (2, '2026-03-14', '11:30', '12:00', 'Heart checkup'),
    (2, '2026-03-14', '16:00', '16:30', 'Evening slot'),
    (2, '2026-03-14', '16:30', '17:00', 'Evening slot'),
    (2, '2026-03-15', '10:00', '10:30', 'Heart checkup'),
    (2, '2026-03-15', '10:30', '11:00', 'Heart checkup'),
    (2, '2026-03-15', '16:00', '16:30', 'Evening slot'),
    (2, '2026-03-15', '16:30', '17:00', 'Evening slot'),

    -- Dr. Rahul Sharma
    (3, '2026-03-11', '15:00', '15:30', 'Vaccination slot'),
    (3, '2026-03-11', '15:30', '16:00', 'Vaccination slot'),
    (3, '2026-03-12', '09:00', '09:30', 'Kids clinic'),
    (3, '2026-03-12', '09:30', '10:00', 'Kids clinic'),
    (3, '2026-03-12', '11:00', '11:30', 'Kids checkup'),
    (3, '2026-03-12', '11:30', '12:00', 'Kids checkup'),
    (3, '2026-03-13', '09:00', '09:30', 'Kids clinic'),
    (3, '2026-03-13', '09:30', '10:00', 'Kids clinic'),
    (3, '2026-03-13', '15:00', '15:30', 'Vaccination slot'),
    (3, '2026-03-13', '15:30', '16:00', 'Vaccination slot'),
    (3, '2026-03-14', '09:00', '09:30', 'Kids clinic'),
    (3, '2026-03-14', '09:30', '10:00', 'Kids clinic'),
    (3, '2026-03-14', '11:00', '11:30', 'Kids checkup'),
    (3, '2026-03-14', '11:30', '12:00', 'Kids checkup'),
    (3, '2026-03-15', '09:00', '09:30', 'Kids clinic'),
    (3, '2026-03-15', '09:30', '10:00', 'Kids clinic'),
    (3, '2026-03-15', '15:00', '15:30', 'Vaccination slot'),
    (3, '2026-03-15', '15:30', '16:00', 'Vaccination slot')

    ON CONFLICT (provider_id, availability_date, start_time, end_time) DO NOTHING;
    """)
)

        await session.commit()





# await session.execute(
# text("""
# INSERT INTO available_slots
# (provider_id, availability_date, start_time, end_time, notes)

# SELECT
#     d.provider_id,
#     day::date AS availability_date,
#     time_slot AS start_time,
#     time_slot + interval '30 minutes' AS end_time,
#     'Auto slot' AS notes
# FROM
#     generate_series('2026-03-13'::date, '2026-03-20'::date, interval '1 day') AS day
# CROSS JOIN
#     (VALUES (1),(2),(3)) AS d(provider_id)
# CROSS JOIN
#     generate_series('09:00'::time, '18:30'::time, interval '30 minutes') AS time_slot
# LIMIT 480

# ON CONFLICT (provider_id, availability_date, start_time, end_time) DO NOTHING;
# """)
# )