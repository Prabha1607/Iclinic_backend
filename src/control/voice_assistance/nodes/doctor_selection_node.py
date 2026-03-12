import json
from src.data.clients.postgres_client import AsyncSessionLocal
from src.data.repositories.generic_crud import bulk_get_instance
from src.data.models.postgres.user import User, ProviderProfile
from src.control.voice_assistance.models import ainvoke_llm, get_llama1
from src.control.voice_assistance.utils import clear_markdown
from src.control.voice_assistance.prompts.doctor_selection_node_prompt import (
    NO_DOCTORS_RESPONSE,
    DOCTOR_CONVERSATION_PROMPT,
    DOCTOR_VERIFIER_PROMPT,
    DOCTOR_INTENT_VERIFIER_PROMPT,
)


async def fetch_doctors(appointment_type_id: int) -> list[dict]:
    async with AsyncSessionLocal() as db:
        users = await bulk_get_instance(User, db, role_id=2, is_active=True, appointment_type_id=appointment_type_id)
        doctor_ids = [u.id for u in users]
        all_profiles = await bulk_get_instance(ProviderProfile, db)
        profile_map = {p.user_id: p for p in all_profiles if p.user_id in doctor_ids}
        return [
            {
                "id": u.id,
                "name": f"Dr. {u.first_name} {u.last_name}",
                "specialization": profile_map[u.id].specialization if u.id in profile_map else "N/A",
                "qualification": profile_map[u.id].qualification if u.id in profile_map else "N/A",
                "experience": profile_map[u.id].experience if u.id in profile_map else 0,
                "bio": profile_map[u.id].bio if u.id in profile_map else "",
            }
            for u in users
        ]


def _doctors_context(doctors: list[dict]) -> str:
    return "\n".join(
        f"{i+1}. id={d['id']} name={d['name']} specialization={d['specialization']} "
        f"experience={d['experience']}yrs qualification={d['qualification']} bio={d['bio']}"
        for i, d in enumerate(doctors)
    )


async def _check_user_intent(user_text: str, doctors: list[dict]) -> str:
    try:
        response = await ainvoke_llm([
            {"role": "system", "content": DOCTOR_INTENT_VERIFIER_PROMPT},
            {"role": "user", "content": f"Doctors:\n{_doctors_context(doctors)}\n\nPatient said: {user_text}"},
        ])
        data = json.loads(clear_markdown(response.content.strip()))
        return data.get("intent", "unknown")
    except Exception as e:
        print("[doctor intent verifier error]:", e)
        return "unknown"


async def _verify_selection(user_text: str, doctors: list[dict]) -> tuple[int | None, str | None]:
    try:
        response = await ainvoke_llm([
            {"role": "system", "content": DOCTOR_VERIFIER_PROMPT},
            {"role": "user", "content": f"Doctors:\n{_doctors_context(doctors)}\n\nPatient said: {user_text}"},
        ])
        data = json.loads(clear_markdown(response.content.strip()))
        doctor_id = data.get("doctor_id")
        doctor_name = data.get("doctor_name")
        return (int(doctor_id), str(doctor_name)) if doctor_id else (None, None)
    except Exception as e:
        print("[doctor verifier error]:", e)
        return None, None


def _build_messages(mode: str, history: list[dict], doctors: list[dict], intent: str, previous_doctor: str | None, change_request: str | None) -> list[dict]:
    seed = history if history else [{"role": "user", "content": "start"}]
    return [
        {
            "role": "system",
            "content": DOCTOR_CONVERSATION_PROMPT.format(
                doctors_context=_doctors_context(doctors),
                intent=intent,
                mode=mode,
                previous_doctor=previous_doctor or "none",
                change_request=change_request or "none",
            ),
        },
        *seed,
    ]


async def doctor_selection_node(state: dict) -> dict:
    print("[doctor_selection_node] -----------------------------")

    user_change_request: str | None = state.get("user_change_request")
    previous_doctor_name: str | None = state.get("doctor_confirmed_name")
    user_text: str = (state.get("speech_user_text") or "").strip()
    history: list[dict] = list(state.get("doctor_selection_history") or [])
    intent: str = state.get("mapping_intent") or "general checkup"

    try:
        doctors = await fetch_doctors(state.get("mapping_appointment_type_id") or -1)
    except Exception as e:
        print("[doctor_selection_node] fetch failed:", e)
        return {**state, "doctor_selection_completed": True, "speech_ai_text": NO_DOCTORS_RESPONSE}

    if not doctors:
        return {**state, "doctor_selection_completed": True, "speech_ai_text": NO_DOCTORS_RESPONSE}

    if user_change_request and previous_doctor_name:
        available_doctors = [d for d in doctors if d["name"] != previous_doctor_name] or doctors
    else:
        available_doctors = doctors

    if user_text:
        history.append({"role": "user", "content": user_text})

    if state.get("doctor_confirmed_id") and not user_change_request:
        if user_text:
            user_intent = await _check_user_intent(user_text, doctors)
            print("[user_intent]:", user_intent)

            if user_intent in ("asking_info", "change_request", "unclear"):
                messages = _build_messages("handle_question", history, doctors, intent, previous_doctor_name, user_change_request)
                llm = get_llama1()
                response = await llm.ainvoke(messages)
                ai_text = response.content.strip().strip('"').strip("'")
                history.append({"role": "assistant", "content": ai_text})
                return {
                    **state,
                    "doctor_selection_history": history,
                    "speech_ai_text": ai_text,
                    "doctor_selection_completed": False,
                }

        return {**state, "doctor_selection_completed": True}

    if len(available_doctors) == 1 and not user_change_request:
        doctor = available_doctors[0]
        messages = _build_messages("auto_select", history, available_doctors, intent, previous_doctor_name, user_change_request)
        llm = get_llama1()
        response = await llm.ainvoke(messages)
        ai_text = response.content.strip().strip('"').strip("'")
        history.append({"role": "assistant", "content": ai_text})
        return {
            **state,
            "user_change_request": None,
            "doctor_confirmed_id": doctor["id"],
            "doctor_confirmed_name": doctor["name"],
            "doctor_selection_pending": False,
            "doctor_selection_completed": True,
            "doctor_selection_history": history,
            "speech_ai_text": ai_text,
        }

    if user_text and state.get("doctor_selection_pending"):
        user_intent = await _check_user_intent(user_text, available_doctors)
        print("[user_intent]:", user_intent)

        if user_intent == "asking_info":
            messages = _build_messages("handle_question", history, available_doctors, intent, previous_doctor_name, user_change_request)
            llm = get_llama1()
            response = await llm.ainvoke(messages)
            ai_text = response.content.strip().strip('"').strip("'")
            history.append({"role": "assistant", "content": ai_text})
            return {
                **state,
                "doctor_selection_history": history,
                "doctor_selection_pending": True,
                "doctor_selection_completed": False,
                "speech_ai_text": ai_text,
            }

        if user_intent == "selecting":
            doctor_id, doctor_name = await _verify_selection(user_text, available_doctors)
            if doctor_id:
                messages = _build_messages("confirm_selection", history, available_doctors, intent, previous_doctor_name, user_change_request)
                llm = get_llama1()
                response = await llm.ainvoke(messages)
                ai_text = response.content.strip().strip('"').strip("'")
                history.append({"role": "assistant", "content": ai_text})
                return {
                    **state,
                    "user_change_request": None,
                    "doctor_confirmed_id": doctor_id,
                    "doctor_confirmed_name": doctor_name,
                    "doctor_selection_completed": True,
                    "doctor_selection_pending": False,
                    "doctor_selection_history": history,
                    "speech_ai_text": ai_text,
                }

    messages = _build_messages("present_options", history, available_doctors, intent, previous_doctor_name, user_change_request)
    llm = get_llama1()
    response = await llm.ainvoke(messages)
    ai_text = response.content.strip().strip('"').strip("'")
    print("[ai_response]:", ai_text)
    history.append({"role": "assistant", "content": ai_text})

    return {
        **state,
        "doctor_selection_pending": True,
        "doctor_selection_completed": False,
        "doctor_list": available_doctors,
        "doctor_selection_history": history,
        "speech_ai_text": ai_text,
    }

