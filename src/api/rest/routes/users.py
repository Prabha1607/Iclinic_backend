from fastapi import APIRouter, Depends, Request, Response, HTTPException,Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
import logging
from src.api.rest.dependencies import get_current_user, get_db
from src.core.services.user import create_patient_service, get_providers, get_providers_by_type_service, get_roles, get_all_patients
from src.schemas.user import PatientFullResponse, ProviderFullResponse, UserCreate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"], dependencies=[Depends(get_current_user)])

@router.get("/get_roles")
async def get_all_roles(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    try:
        result = await get_roles(db=db)
        return result

    except Exception as e:
        logger.error("Failed to fetch roles", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to fetch roles")


@router.get("/list", response_model=list[PatientFullResponse])
async def get_patients(
    request: Request,
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, le=100),
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db)
):
    try:
        users = await get_all_patients(
            db=db,
            page=page,
            page_size=page_size,
            is_active=is_active,
        )

        return users

    except Exception as e:
        logger.error("Failed to fetch patients", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to fetch patients")


@router.get("/providers", response_model=list[ProviderFullResponse])
async def get_all_providers(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, le=100),
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db)
):
    providers = await get_providers(
        db, page, page_size, is_active
    )
    return providers


@router.get("/providers/by-type", response_model=list[ProviderFullResponse])
async def get_providers_by_type(
    appointment_type_id: int,
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db)
):
    providers = await get_providers_by_type_service(
        db=db,
        appointment_type_id=appointment_type_id,
        is_active=is_active
    )
    return providers

@router.post("/patients/create", response_model=PatientFullResponse)
async def create_patient(
    patient: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    try:
        created_patient = await create_patient_service(db=db, patient_data=patient)
        return created_patient
    except IntegrityError:
        raise HTTPException(
            status_code=400,
            detail="Email or phone already exists"
        )
    except Exception as e:
        print("CREATE PATIENT ERROR:", e)
        raise
        

from src.schemas.user import UserUpdate
from src.core.services.user import update_user_service


@router.put("/update/{user_id}", response_model=PatientFullResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db)
):
    try:
        user = await update_user_service(
            db=db,
            user_id=user_id,
            user_data=user_data
        )
        return user

    except IntegrityError:
        raise HTTPException(
            status_code=400,
            detail="Email already exists"
        )

    except Exception as e:
        logger.error("Failed to update user", extra={"error": str(e)})
        print("UPDATE USER ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))


