from pydantic import BaseModel, Field, EmailStr , field_validator
from datetime import datetime,date
from typing import Optional
import re

class PatientProfileCreate(BaseModel):
    date_of_birth: date
    gender: str
    address: Optional[str] = None
    preferred_language: Optional[str] = None

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    role_id: int = Field(..., description="Role ID of the user")
    country_code: str = Field(..., pattern=r"^\+\d{1,4}$")
    email: EmailStr
    phone_no: str = Field(..., pattern=r"^\d{7,15}$")
    password: str = Field(..., description="Password with at least 6 chars, one uppercase, one number, one special symbol.")
    patient_profile: Optional[PatientProfileCreate] = None   # ← add this

    @field_validator("password")
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters long.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one number.")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>/?~]", v):
            raise ValueError("Password must contain at least one special character.")
        return v

    model_config = {"from_attributes": True}

    
class UserLogin(BaseModel):
    identifier : str
    password : str

    @field_validator("identifier")
    def validate_identifier(cls , v):
        email_pattern = r"^[^@]+@[^@]+\.[^@]+$"
        phone_pattern = r"^\+?\d{7,15}$"

        if not re.match(email_pattern, v) and not re.match(phone_pattern, v):
            raise ValueError("Identifier must be a valid email or phone number")

        return v
    
class UserResponse(BaseModel):
    id: int
    role_id: int
    appointment_type_id: Optional[int] = None

    first_name: str
    last_name: str
    country_code: str
    phone_no: str
    email: EmailStr

    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }


from datetime import date
from pydantic import BaseModel, computed_field


class PatientProfileResponse(BaseModel):
    id: int
    user_id: int
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    preferred_language: Optional[str] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class PatientFullResponse(BaseModel):
    id: int
    role_id: int
    appointment_type_id: Optional[int] = None

    first_name: str
    last_name: str
    country_code: str
    phone_no: str
    email: EmailStr

    is_active: bool
    created_at: datetime
    updated_at: datetime

    patient_profile: Optional[PatientProfileResponse] = None

    model_config = {
        "from_attributes": True
    }


class ProviderProfileResponse(BaseModel):
    id: int
    user_id: int
    specialization: Optional[str]
    qualification: Optional[str]
    experience: Optional[int]
    bio: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProviderFullResponse(UserResponse):
    provider_profile: Optional[ProviderProfileResponse] = None

    model_config = {"from_attributes": True}
    
class PatientProfileUpdate(BaseModel):
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    preferred_language: Optional[str] = None

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    patient_profile: Optional[PatientProfileUpdate] = None  # ← key addition

    @field_validator("password")
    def validate_password(cls, v):
        if v is None:
            return v
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters long.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain one uppercase letter.")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain one number.")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>/?~]", v):
            raise ValueError("Password must contain one special character.")
        return v

    model_config = {"from_attributes": True}