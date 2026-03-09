from fastapi import APIRouter, FastAPI
from src.data.seeds.seed_users import seed_users
from src.api.rest.routes import available_slots
from src.api.rest.routes import appointments
from src.api.rest.routes import appointment_types
from src.api.rest.routes import auth
from src.api.rest.routes import voice
from src.api.rest.routes import users
from src.api.middleware.cors import add_cors_middleware
from src.api.middleware.logging import logging_middleware, setup_logging
from src.api.middleware.auth import AuthorizationMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from src.data.clients.postgres_client import init_db
from contextlib import asynccontextmanager
from src.data.seeds.seed_roles import seed_roles 
from src.data.seeds.seed_appointment_types import seed_appointment_types
from src.data.seeds.seed_doctors import seed_doctors
from src.data.seeds.seed_available_slots import seed_available_slots


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_db()
    await seed_roles()
    await seed_appointment_types()
    await seed_doctors()
    await seed_users()
    await seed_available_slots()

    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(AuthorizationMiddleware)
app.add_middleware(BaseHTTPMiddleware, dispatch = logging_middleware)

add_cors_middleware(app)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(router=auth.router)
api_router.include_router(router = voice.router)
api_router.include_router(router = users.router)
api_router.include_router(router = appointments.router)
api_router.include_router(router = available_slots.router)
api_router.include_router(router=appointment_types.router)

app.include_router(router=api_router)
