from pydantic import BaseModel
from datetime import datetime, date, time
from typing import Optional
from src.data.models.postgres.ENUM import SlotStatus


class AvailableSlotResponse(BaseModel):
    id: int
    provider_id: int

    availability_date: date
    start_time: time
    end_time: time

    status: SlotStatus

    created_by: Optional[int] = None
    notes: Optional[str] = None

    is_active: bool

    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }


