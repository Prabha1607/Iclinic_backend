import asyncio
from src.data.clients.postgres_client import AsyncSessionLocal
from src.data.models.postgres.appointment import Appointment
from src.data.models.postgres.appointment_type import AppointmentType
from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.user import ProviderProfile, User
from src.data.repositories.generic_crud import bulk_get_instance

_cache: dict = {}
_cache_lock = asyncio.Lock()


async def _load_cache() -> None:
    async with AsyncSessionLocal() as db:
        all_doctors      = await bulk_get_instance(User, db, role_id=2, is_active=True)
        all_profiles     = await bulk_get_instance(ProviderProfile, db)
        all_slots        = await bulk_get_instance(AvailableSlot, db, is_active=True)
        all_appointments = await bulk_get_instance(Appointment, db, is_active=True)
        all_appt_types   = await bulk_get_instance(AppointmentType, db)

        # ── pre-join: attach type_name to every appointment ──────────────────
        type_map = {t.id: t.name for t in all_appt_types}
        joined_appointments = [
            (appt, type_map.get(appt.appointment_type_id, "N/A"))
            for appt in all_appointments
        ]

    _cache["doctors"]             = {u.id: u for u in all_doctors}
    _cache["profiles"]            = {p.user_id: p for p in all_profiles}
    _cache["slots"]               = all_slots
    _cache["appointments"]        = all_appointments
    _cache["joined_appointments"] = joined_appointments 


    
async def ensure_cache() -> None:
    async with _cache_lock:
        if "doctors" not in _cache:
            await _load_cache()


def clear_cache() -> None:
    _cache.clear()