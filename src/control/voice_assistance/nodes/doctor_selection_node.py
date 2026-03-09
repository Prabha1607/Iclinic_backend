import json
from src.data.clients.postgres_client import AsyncSessionLocal
from src.data.repositories.generic_crud import bulk_get_instance
from src.data.models.postgres.user import User, ProviderProfile
from src.control.voice_assistance.models import get_llama1
from src.control.voice_assistance.utils import clear_markdown
from src.control.voice_assistance.prompts.doctor_selection_node_prompt import (
    NO_DOCTORS_RESPONSE,
    DOCTOR_MATCH_SYSTEM_PROMPT,
)


DOCTOR_SPEECH_SYSTEM = """
You are a warm, conversational medical appointment assistant on a voice call.
Your job is to generate natural, spoken responses — no markdown, no bullet points, no lists.
Keep responses concise and friendly, as if speaking aloud.
Respond with ONLY valid JSON, no explanation:
{"speech": "<your spoken response>"}
""".strip()


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


def _build_doctor_list_lines(doctors: list[dict]) -> str:
    return "\n".join(
        f"{i+1}. {d['name']} — {d['specialization']}, {d['experience']} years experience, {d['qualification']}"
        for i, d in enumerate(doctors)
    )


def _build_doctors_context(doctors: list[dict]) -> str:
    return "\n".join(
        f"{i+1}. id={d['id']} name={d['name']} specialization={d['specialization']} experience={d['experience']}yrs"
        for i, d in enumerate(doctors)
    )


async def _llm_speech(prompt: str, fallback: str) -> str:
    try:
        llm = get_llama1()
        response = await llm.ainvoke([
            ("system", DOCTOR_SPEECH_SYSTEM),
            ("human", prompt),
        ])
        parsed = json.loads(clear_markdown(response.content.strip()))
        return parsed.get("speech") or fallback
    except Exception as e:
        print(f"[doctor_selection_node] _llm_speech failed: {e}")
        return fallback


async def _auto_select_state(state: dict, doctor: dict, user_change_request: str | None) -> dict:
    context = (
        f"The patient previously requested a change: \"{user_change_request}\". "
        if user_change_request else ""
    )
    prompt = (
        f"{context}"
        f"There is only one available doctor: {doctor['name']}, {doctor['specialization']}, "
        f"{doctor['experience']} years of experience, {doctor['qualification']}. "
        "Inform the patient naturally that this doctor will be seeing them and that you'll now finalize the appointment."
    )
    fallback = (
        f"You'll be seeing {doctor['name']}, {doctor['specialization']} "
        f"with {doctor['experience']} years of experience. "
        "Let me now finalize your appointment."
    )
    speech = await _llm_speech(prompt, fallback)
    return {
        **state,
        "user_change_request":        None,
        "doctor_confirmed_id":        doctor["id"],
        "doctor_confirmed_name":      doctor["name"],
        "doctor_selection_pending":   False,
        "doctor_selection_completed": True,
        "speech_ai_text":             speech,
    }


async def _present_doctors_state(
    state: dict,
    doctors: list[dict],
    intent: str,
    user_change_request: str | None,
    previous_doctor_name: str | None,
) -> dict:
    if user_change_request and previous_doctor_name:
        filtered_doctors = [d for d in doctors if d["name"] != previous_doctor_name]
    else:
        filtered_doctors = doctors

    if not filtered_doctors:
        filtered_doctors = doctors

    doctor_list_lines = _build_doctor_list_lines(filtered_doctors)
    context = (
        f"The patient previously chose {previous_doctor_name} but now wants to change. "
        f"Their change request: \"{user_change_request}\". "
        if user_change_request and previous_doctor_name
        else ""
    )
    prompt = (
        f"{context}"
        f"The patient's concern is: {intent.replace('_', ' ')}. "
        f"Here are the available doctors:\n{doctor_list_lines}\n"
        "Introduce these doctors conversationally and ask the patient which one they'd prefer. "
        "Do not use numbered lists or bullet points — speak naturally."
    )
    fallback = (
        f"Based on your {intent.replace('_', ' ')} concern, here are our available doctors: "
        f"{doctor_list_lines}. Which doctor would you prefer?"
    )
    speech = await _llm_speech(prompt, fallback)
    return {
        **state,
        "doctor_selection_pending":   True,
        "doctor_selection_completed": False,
        "doctor_list":                filtered_doctors,
        "speech_ai_text":             speech,
    }


async def _confirmed_doctor_state(
    state: dict,
    doctor_id: int,
    doctor_name: str,
    user_change_request: str | None,
) -> dict:
    context = (
        f"The patient had previously requested a change: \"{user_change_request}\". "
        if user_change_request else ""
    )
    prompt = (
        f"{context}"
        f"The patient has chosen {doctor_name}. "
        "Confirm this selection warmly and let them know you'll now finalize the appointment."
    )
    fallback = (
        f"Great! I've noted {doctor_name} as your doctor. "
        "Let me now finalize your appointment."
    )
    speech = await _llm_speech(prompt, fallback)
    return {
        **state,
        "user_change_request":        None,
        "doctor_confirmed_id":        doctor_id,
        "doctor_confirmed_name":      doctor_name,
        "doctor_selection_completed": True,
        "doctor_selection_pending":   False,
        "speech_ai_text":             speech,
    }


async def _match_doctor_from_response(
    user_text: str, intent: str, doctors: list[dict]
) -> tuple[int, str]:
    doctors_context = _build_doctors_context(doctors)
    try:
        llm = get_llama1()
        response = await llm.ainvoke([
            ("system", DOCTOR_MATCH_SYSTEM_PROMPT),
            ("human", f"Doctors:\n{doctors_context}\n\nPatient intent: {intent}\nPatient said: {user_text}\n\nPick the best match."),
        ])
        parsed = json.loads(clear_markdown(response.content.strip()))
        return int(parsed["doctor_id"]), str(parsed["doctor_name"])
    except Exception:
        return doctors[0]["id"], doctors[0]["name"]


async def doctor_selection_node(state: dict) -> dict:
    print("[doctor_selection_node] -----------------------------")

    user_change_request: str | None  = state.get("user_change_request")
    previous_doctor_name: str | None = state.get("doctor_confirmed_name")

    if state.get("doctor_confirmed_id") and not user_change_request:
        return {**state, "doctor_selection_completed": True}

    try:
        doctors = await fetch_doctors(state.get("mapping_appointment_type_id") or -1)
    except Exception as e:
        print(f"[doctor_selection_node] Failed to fetch doctors: {e}")
        return {
            **state,
            "doctor_selection_completed": True,
            "speech_ai_text": NO_DOCTORS_RESPONSE,
        }

    if not doctors:
        return {
            **state,
            "doctor_selection_completed": True,
            "speech_ai_text": NO_DOCTORS_RESPONSE,
        }

    intent = state.get("mapping_intent", "general checkup")

    if len(doctors) == 1:
        return await _auto_select_state(state, doctors[0], user_change_request)

    if not state.get("doctor_selection_pending"):
        return await _present_doctors_state(
            state, doctors, intent, user_change_request, previous_doctor_name
        )

    user_text: str = (state.get("speech_user_text") or "").strip()
    filtered_doctors = (
        [d for d in doctors if d["name"] != previous_doctor_name] or doctors
        if user_change_request and previous_doctor_name
        else doctors
    )

    doctor_id, doctor_name = await _match_doctor_from_response(user_text, intent, filtered_doctors)
    print(f"[doctor_selection_node] selected doctor: id={doctor_id}, name={doctor_name}")

    return await _confirmed_doctor_state(state, doctor_id, doctor_name, user_change_request)


