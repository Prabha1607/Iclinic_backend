from fastapi import Depends
from src.data.repositories.generic_crud import bulk_get_instance
from src.data.models.postgres.appointment_type import AppointmentType
from src.api.rest.dependencies import get_db
from sqlalchemy.ext.asyncio import AsyncSession

async def get_appointment_types(db: AsyncSession):
    try:
        return await bulk_get_instance(
            model=AppointmentType,
            db=db,
            is_active=True
        )
    except Exception:
        raise Exception("Failed to fetch appointment types")
    

    