from sqlalchemy import select
from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.ENUM import SlotStatus
from sqlalchemy.ext.asyncio import AsyncSession


async def get_provider_slots_repo(
    db: AsyncSession,
    provider_id: int
):

    stmt = (
        select(AvailableSlot)
        .where(
            AvailableSlot.provider_id == provider_id,
            AvailableSlot.status == SlotStatus.AVAILABLE,
            AvailableSlot.is_active == True
        )
    )

    result = await db.execute(stmt)

    return result.scalars().all()

