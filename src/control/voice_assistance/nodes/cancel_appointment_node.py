from datetime import datetime, timezone, date as date_type
from sqlalchemy import select, and_
from src.data.clients.postgres_client import AsyncSessionLocal
from src.data.models.postgres.appointment import Appointment
from src.data.models.postgres.appointment_type import AppointmentType
from src.data.models.postgres.ENUM import AppointmentStatus
from src.control.voice_assistance.models import get_llama1
from src.control.voice_assistance.utils import update_state
from src.data.repositories.generic_crud import update_instance
from src.control.voice_assistance.prompts.cancel_appointment_node_prompt import (
    SELECT_SLOT_PROMPT,
    SELECT_DATE_PROMPT,
    CONFIRM_PROMPT,
    ERROR_RESPONSE,
    DB_ERROR_RESPONSE,
    CANCEL_ERROR_RESPONSE,
    NO_APPOINTMENTS_RESPONSE,
)

async def _fetch_upcoming_appointments(user_id: int) -> list:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Appointment, AppointmentType.name.label("type_name"))
            .join(AppointmentType, Appointment.appointment_type_id == AppointmentType.id)
            .where(
                and_(
                    Appointment.user_id == user_id,   # ✅ FIXED HERE
                    Appointment.status == AppointmentStatus.SCHEDULED,
                    Appointment.is_active == True,
                    Appointment.scheduled_date >= date_type.today(),
                )
            )
            .order_by(Appointment.scheduled_date.asc(), Appointment.scheduled_start_time.asc())
        )
        result = await session.execute(stmt)
        rows = result.all()

    return [
        row for row in rows
        if datetime.combine(
            row[0].scheduled_date,
            row[0].scheduled_start_time,
        ).replace(tzinfo=timezone.utc) > now
    ]

async def _cancel_appointment_in_db(appointment_id: int) -> None:
    async with AsyncSessionLocal() as session:
        await update_instance(
            id=appointment_id,
            model=Appointment,
            db=session,
            status=AppointmentStatus.CANCELLED,
            cancelled_at=datetime.now(timezone.utc),
            cancellation_reason="Cancelled via voice assistant",
            is_active=False,
        )


async def _llm_invoke(system: str, human: str) -> str:
    model = get_llama1()
    response = await model.ainvoke([("system", system), ("human", human)])
    return response.content.strip()


def _build_appointments_list(rows: list) -> list[dict]:
    return [
        {
            "id":         appointment.id,
            "date":       str(appointment.scheduled_date),
            "start_time": str(appointment.scheduled_start_time),
            "end_time":   str(appointment.scheduled_end_time),
            "reason":     appointment.reason_for_visit or "Not specified",
            "type_name":  type_name,
        }
        for appointment, type_name in rows
    ]


def _reason_line(chosen: dict) -> str:
    return (
        f"The reason you booked this was: {chosen['reason']}. "
        if chosen["reason"] != "Not specified"
        else ""
    )


def _spoken_slots(appointments_list: list[dict]) -> str:
    return ", ".join(
        f"{i+1}. {a['type_name']} from {a['start_time']} to {a['end_time']}"
        for i, a in enumerate(appointments_list)
    )


def _unique_dates(appointments_list: list[dict]) -> list[str]:
    seen = []
    for a in appointments_list:
        if a["date"] not in seen:
            seen.append(a["date"])
    return seen


async def _handle_initial(state: dict, user_id: int) -> dict:
    try:
        rows = await _fetch_upcoming_appointments(user_id)
        print(f"[cancel_appointment_node] Upcoming appointments: {len(rows)}")
    except Exception as e:
        print(f"[cancel_appointment_node] DB ERROR: {type(e).__name__}: {e}")
        return update_state(state, speech_ai_text=DB_ERROR_RESPONSE, cancellation_complete=True)

    if not rows:
        return update_state(
            state,
            cancellation_complete=True,
            speech_ai_text=NO_APPOINTMENTS_RESPONSE,
        )

    appointments_list = _build_appointments_list(rows)
    dates             = _unique_dates(appointments_list)
    date_lines        = "\n".join(f"  - {d}" for d in dates)

    if len(dates) == 1:
        return update_state(
            state,
            appointments_list=appointments_list,
            cancellation_stage="ask_slot" if len(appointments_list) > 1 else "ask_confirm",
            cancellation_appointment=appointments_list[0] if len(appointments_list) == 1 else None,
            speech_ai_text=(
                f"You have an upcoming appointment on {dates[0]}. "
                f"{_spoken_slots(appointments_list)}. "
                f"Which one would you like to cancel?"
            ) if len(appointments_list) > 1 else (
                f"You have one upcoming appointment on {dates[0]}: "
                f"{appointments_list[0]['type_name']} from {appointments_list[0]['start_time']} "
                f"to {appointments_list[0]['end_time']}. "
                f"{_reason_line(appointments_list[0])}"
                f"Would you like to cancel this appointment?"
            ),
        )

    return update_state(
        state,
        appointments_list=appointments_list,
        cancellation_stage="ask_date",
        speech_ai_text=(
            f"You have upcoming appointments on the following dates:\n{date_lines}\n"
            "Which date would you like to cancel?"
        ),
    )


async def _handle_ask_date(state: dict, user_text: str) -> dict:
    appointments_list = state.get("appointments_list", [])
    dates             = _unique_dates(appointments_list)

    if not user_text:
        date_lines = "\n".join(f"  - {d}" for d in dates)
        return update_state(
            state,
            speech_ai_text=f"Please tell me which date. Available dates:\n{date_lines}",
        )

    try:
        dates_list = "\n".join(f"  - {d}" for d in dates)
        matched_date = await _llm_invoke(
            system=SELECT_DATE_PROMPT.format(dates_list=dates_list, user_text=user_text),
            human=user_text,
        )
        print(f"[cancel_appointment_node] Matched date: '{matched_date}'")
    except Exception as e:
        print(f"[cancel_appointment_node] LLM ERROR: {type(e).__name__}: {e}")
        return update_state(state, speech_ai_text=ERROR_RESPONSE, cancellation_complete=True)

    if matched_date == "UNKNOWN":
        date_lines = "\n".join(f"  - {d}" for d in dates)
        return update_state(
            state,
            speech_ai_text=(
                f"I couldn't understand that date. Your upcoming appointments are on:\n{date_lines}\n"
                "Which date would you like to cancel?"
            ),
        )

    slots_on_date = [a for a in appointments_list if a["date"] == matched_date]

    if not slots_on_date:
        date_lines = "\n".join(f"  - {d}" for d in dates)
        return update_state(
            state,
            speech_ai_text=(
                f"I couldn't find any appointments on {matched_date}. "
                f"Your upcoming appointments are on:\n{date_lines}\n"
                "Which date would you like to cancel?"
            ),
        )

    if len(slots_on_date) == 1:
        chosen = slots_on_date[0]
        return update_state(
            state,
            cancellation_appointment=chosen,
            cancellation_stage="ask_confirm",
            speech_ai_text=(
                f"I found your {chosen['type_name']} appointment on {chosen['date']} "
                f"from {chosen['start_time']} to {chosen['end_time']}. "
                f"{_reason_line(chosen)}"
                f"Are you sure you want to cancel this appointment?"
            ),
        )

    return update_state(
        state,
        cancellation_stage="ask_slot",
        speech_ai_text=(
            f"You have {len(slots_on_date)} appointments on {matched_date}. "
            f"{_spoken_slots(slots_on_date)}. "
            f"Which time slot would you like to cancel?"
        ),
    )


async def _handle_ask_slot(state: dict, user_text: str) -> dict:
    appointments_list = state.get("appointments_list", [])

    if not user_text:
        return update_state(state, speech_ai_text="Please say which time slot you would like to cancel.")

    try:
        slots_text    = "\n".join(
            f"{i+1}. {a['type_name']} from {a['start_time']} to {a['end_time']}"
            for i, a in enumerate(appointments_list)
        )
        matched_index = await _llm_invoke(
            system=SELECT_SLOT_PROMPT.format(
                date=appointments_list[0]["date"] if appointments_list else "",
                slots_list=slots_text,
                user_text=user_text,
            ),
            human=user_text,
        )
        print(f"[cancel_appointment_node] LLM matched slot index: '{matched_index}'")
    except Exception as e:
        print(f"[cancel_appointment_node] LLM ERROR: {type(e).__name__}: {e}")
        return update_state(state, speech_ai_text=ERROR_RESPONSE, cancellation_complete=True)

    if matched_index == "UNKNOWN":
        spoken = ", ".join(
            f"{i+1}. {a['start_time']} to {a['end_time']}"
            for i, a in enumerate(appointments_list)
        )
        return update_state(state, speech_ai_text=f"I could not understand. Please say one of these slots: {spoken}.")

    try:
        chosen = appointments_list[int(matched_index) - 1]
    except (ValueError, IndexError):
        return update_state(
            state,
            speech_ai_text="I could not find that slot. Please say the time or number of the appointment you want to cancel.",
        )

    return update_state(
        state,
        cancellation_appointment=chosen,
        cancellation_stage="ask_confirm",
        speech_ai_text=(
            f"You selected the {chosen['type_name']} appointment "
            f"from {chosen['start_time']} to {chosen['end_time']} on {chosen['date']}. "
            f"{_reason_line(chosen)}"
            f"Are you sure you want to cancel this appointment?"
        ),
    )


async def _handle_ask_confirm(state: dict, user_text: str) -> dict:
    appointment_data = state.get("cancellation_appointment")

    if not user_text:
        return update_state(state, speech_ai_text="Please confirm. Do you want to cancel this appointment?")

    try:
        decision = await _llm_invoke(
            system=CONFIRM_PROMPT.format(
                date=appointment_data["date"],
                start_time=appointment_data["start_time"],
                end_time=appointment_data["end_time"],
                appointment_type=appointment_data["type_name"],
                reason=appointment_data["reason"],
                user_text=user_text,
            ),
            human=user_text,
        )
        print(f"[cancel_appointment_node] Decision: '{decision}'")
    except Exception as e:
        print(f"[cancel_appointment_node] LLM ERROR: {type(e).__name__}: {e}")
        return update_state(state, speech_ai_text=ERROR_RESPONSE, cancellation_complete=True)

    if decision.upper() != "YES":
        return update_state(
            state,
            cancellation_stage="done",
            cancellation_complete=True,
            speech_ai_text="Okay, your appointment remains scheduled. Is there anything else I can help you with?",
        )

    try:
        await _cancel_appointment_in_db(appointment_data["id"])
        print("[cancel_appointment_node] Appointment cancelled in DB")
    except Exception as e:
        print(f"[cancel_appointment_node] DB ERROR: {type(e).__name__}: {e}")
        return update_state(state, speech_ai_text=CANCEL_ERROR_RESPONSE, cancellation_complete=True)

    return update_state(
        state,
        cancellation_stage="done",
        cancellation_complete=True,
        speech_ai_text=(
            f"Your {appointment_data['type_name']} appointment on {appointment_data['date']} "
            f"from {appointment_data['start_time']} to {appointment_data['end_time']} "
            f"has been successfully cancelled."
        ),
    )


async def cancel_appointment_node(state: dict) -> dict:
    print("[cancel_appointment_node] -----------------------------")

    user_id   = state.get("identity_patient_id")
    user_text = state.get("speech_user_text")
    stage     = state.get("cancellation_stage")

    print(f"[cancel_appointment_node] user_id={user_id}, stage={stage}, user_text={user_text}")

    if stage is None:
        return await _handle_initial(state, user_id)

    if stage == "ask_date":
        return await _handle_ask_date(state, user_text)

    if stage == "ask_slot":
        return await _handle_ask_slot(state, user_text)

    if stage == "ask_confirm":
        return await _handle_ask_confirm(state, user_text)

    print(f"[cancel_appointment_node] WARNING: Unhandled stage='{stage}'")
    return state



