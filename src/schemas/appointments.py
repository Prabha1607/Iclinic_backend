from pydantic import BaseModel, Field, field_validator
from datetime import date, time, datetime
from typing import Optional
from src.data.models.postgres.ENUM import AppointmentStatus, BookingChannel


class AppointmentCreate(BaseModel):
    user_id: int
    provider_id: int
    appointment_type_id: int
    availability_slot_id: int

    patient_name: str = Field(..., min_length=1, max_length=150)

    scheduled_date: date
    scheduled_start_time: time
    scheduled_end_time: time

    reason_for_visit: Optional[str] = None
    notes: Optional[str] = None

    booking_channel: Optional[BookingChannel] = None
    instructions: Optional[str] = None

    @field_validator("scheduled_end_time")
    def validate_time_order(cls, end_time, values):
        start_time = values.data.get("scheduled_start_time")
        if start_time and end_time <= start_time:
            raise ValueError("End time must be greater than start time")
        return end_time

    model_config = {
        "from_attributes": True
    }


class AppointmentUpdate(BaseModel):
    scheduled_date: Optional[date] = None
    scheduled_start_time: Optional[time] = None
    scheduled_end_time: Optional[time] = None

    reason_for_visit: Optional[str] = None
    notes: Optional[str] = None
    instructions: Optional[str] = None
    booking_channel: Optional[BookingChannel] = None

    model_config = {
        "from_attributes": True
    }

class AppointmentCancel(BaseModel):
    cancellation_reason: str = Field(..., min_length=3, max_length=500)

    model_config = {
        "from_attributes": True
    }



class ProviderProfileResponse(BaseModel):
    specialization: Optional[str] = None
    qualification: Optional[str] = None
    experience: Optional[int] = None
    bio: Optional[str] = None

    model_config = {
        "from_attributes": True
    }


class UserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    phone_no: str

    model_config = {
        "from_attributes": True
    }


class ProviderResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    phone_no: str

    provider_profile: Optional[ProviderProfileResponse] = None

    model_config = {
        "from_attributes": True
    }


class AppointmentTypeResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    duration_minutes: int
    instructions: Optional[str] = None

    model_config = {
        "from_attributes": True
    }


class AppointmentResponse(BaseModel):
    id: int
    user_id: int
    provider_id: int
    appointment_type_id: int
    availability_slot_id: int

    patient_name: str

    scheduled_date: date
    scheduled_start_time: time
    scheduled_end_time: time

    status: AppointmentStatus

    reason_for_visit: Optional[str] = None
    notes: Optional[str] = None

    booking_channel: Optional[BookingChannel] = None
    instructions: Optional[str] = None

    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None

    created_at: datetime
    updated_at: Optional[datetime] = None

    user: Optional[UserResponse] = None
    provider: Optional[ProviderResponse] = None
    appointment_type: Optional[AppointmentTypeResponse] = None

    model_config = {
        "from_attributes": True
    }