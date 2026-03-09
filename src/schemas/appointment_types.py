from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class AppointmentTypeResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    duration_minutes: int
    instructions: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }