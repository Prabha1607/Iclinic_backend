import json
from typing import Any, Dict, Optional, Tuple

from twilio.twiml.voice_response import Gather, Say

from src.config.settings import settings
from src.control.voice_assistance.models import ainvoke_llm
from src.control.voice_assistance.prompts.confirmation_node_prompt import (
    CONVERSATION_PROMPT,
    VERIFIER_PROMPT,
)


# ── State ─────────────────────────────────────────────────────────────────────

def update_state(state: dict, **kwargs: Any) -> dict:
    updates = {k: v for k, v in kwargs.items() if v is not None}
    return {**state, **updates}


def fresh_state(
    call_to_number=None,
    call_sid=None,
    identity_user_name=None,
    identity_user_email=None,
    identity_user_phone=None,
    identity_patient_id=None,
    appointment_types=None,
) -> dict:
    return {
        "call_to_number":  call_to_number,
        "call_sid":        call_sid,
        "call_user_token": None,

        "speech_user_text": None,
        "speech_ai_text":   None,
        "speech_error":     None,

        "service_type": None,

        "identity_user_name":  identity_user_name,
        "identity_user_email": identity_user_email,
        "identity_user_phone": identity_user_phone,
        "identity_patient_id": identity_patient_id,

        "identity_confirmation_completed": False,
        "identity_confirmed_user":         False,
        "identity_confirm_stage":          None,
        "identity_speak_final":            False,
        "identity_phone_verified":         False,

        "clarify_step":                 0,
        "clarify_conversation_history": [],
        "clarify_covered_topics":       [],
        "clarify_completed":            False,
        "clarify_symptoms_text":        None,

        "mapping_intent":                     None,
        "mapping_emergency":                  False,
        "mapping_appointment_type_completed": False,
        "mapping_appointment_type_id":        None,
        "appointment_types":                  appointment_types,
        "appointments_list":                  None,

        "doctor_list":                None,
        "doctor_selection_pending":   False,
        "doctor_selection_completed": False,
        "doctor_confirmed_id":        None,
        "doctor_confirmed_name":      None,

        "slot_stage":               None,
        "slot_selection_completed": False,
        "slot_chosen_date":         None,
        "slot_chosen_period":       None,
        "slot_available_list":      None,
        "slot_selected":            None,
        "slot_selected_start_time": None,
        "slot_selected_end_time":   None,
        "slot_selected_display":    None,
        "slot_booked_id":           None,
        "slot_booked_display":      None,

        "pre_confirmation_completed": False,

        "booking_appointment_completed": False,
        "booking_reason_for_visit":      None,
        "booking_notes":                 None,
        "booking_instructions":          None,
        "booking_awaiting_confirmation": False,
        "booking_context_snapshot":      None,

        "cancellation_stage":       None,
        "cancellation_appointment": None,
        "cancellation_complete":    False,
    }


# ── LLM helpers ───────────────────────────────────────────────────────────────

def clear_markdown(raw: str) -> str:
    if raw.startswith("```"):
        return "\n".join(
            line for line in raw.splitlines()
            if "```" not in line
        ).strip()
    return raw.strip()


async def is_emergency(text: str, get_llama, system_prompt: str) -> bool:
    try:
        model = get_llama()
        response = await model.ainvoke([
            ("system", system_prompt),
            ("human", text),
        ])
        return response.content.strip().upper() == "EMERGENCY"
    except Exception as exc:
        print("is_emergency error:", str(exc))
        return False


async def generate_next_response(
    conversation: str,
    uncovered_topics: list[str],
    model: Any,
    system_prompt: str,
) -> str:
    topics_str = "\n".join(f"- {t}" for t in uncovered_topics) if uncovered_topics else "None — all covered."

    prompt = f"""Conversation so far:
{conversation if conversation.strip() else "(No conversation yet — warmly thank the patient for confirming their name and phone number, then ask about their main symptom.)"}

Topics still not covered:
{topics_str}

Generate your next response now."""

    try:
        response = await model([
            ("system", system_prompt),
            ("human", prompt),
        ])
        return response.content.strip().strip('"').strip("'")
    except Exception as exc:
        print("generate_next_response error:", str(exc))
        return "Could you tell me a bit more about what brings you in today?"


# ── Conversation helpers ──────────────────────────────────────────────────────

def build_conversation_string(history: list[dict]) -> str:
    lines = []
    for turn in history:
        role = "Agent" if turn.get("role") == "agent" else "Patient"
        lines.append(f"{role}: {turn.get('text', '')}")
    return "\n".join(lines)


def build_symptoms_text(history: list[dict], topics: list[str]) -> str:
    patient_turns = [t["text"] for t in history if t.get("role") == "patient"]
    pairs = [
        f"Q: {topic.capitalize()}\nA: {patient_turns[i] if i < len(patient_turns) else 'Not provided'}"
        for i, topic in enumerate(topics)
    ]
    return "\n\n".join(pairs)


def prepare_conversation_history(state: Dict[str, Any], user_text: str) -> list:
    conversation_history = list(state.get("clarify_conversation_history") or [])
    if user_text:
        print("[user_response]:", user_text)
        conversation_history.append({"role": "user", "content": user_text})
    return conversation_history


# ── Confirmation helpers ──────────────────────────────────────────────────────

async def generate_conversation_response(
    patient_name: str,
    phone_number: str,
    user_text: str,
) -> str:
    messages = [
        {
            "role": "system",
            "content": CONVERSATION_PROMPT.format(name=patient_name, phone=phone_number),
        },
        {"role": "user", "content": user_text or "start"},
    ]
    response = await ainvoke_llm(messages)
    return response.content.strip()


async def verify_user_identity(
    user_text: str,
) -> Tuple[bool, bool, Optional[str], Optional[str]]:
    verify_messages = [
        {"role": "system", "content": VERIFIER_PROMPT},
        {"role": "user", "content": f"Latest user reply: {user_text}"},
    ]
    response = await ainvoke_llm(verify_messages)
    data = json.loads(clear_markdown(response.content.strip()))

    return (
        bool(data.get("confirmed", False)),
        bool(data.get("end_call", False)),
        data.get("corrected_name"),
        data.get("corrected_phone"),
    )


def apply_corrections(
    state: Dict[str, Any],
    corrected_name: Optional[str],
    corrected_phone: Optional[str],
) -> Dict[str, Any]:
    if corrected_name:
        state["identity_user_name"] = corrected_name
    if corrected_phone:
        state["identity_user_phone"] = corrected_phone
    return state


# ── Twilio helpers ────────────────────────────────────────────────────────────

def say(parent, text: str) -> None:
    ssml = f'<speak><prosody rate="{settings.SPEAKING_RATE}">{text}</prosody></speak>'
    parent.append(Say(message=ssml, voice=settings.VOICE))


def make_gather() -> Gather:
    return Gather(
        input="speech",
        action="/api/v1/voice/voice-response",
        method="POST",
        speech_timeout=settings.SPEECH_TIMEOUT,
        timeout=settings.GATHER_TIMEOUT,
        action_on_empty_result=settings.ACTION_ON_EMPTY_RESULT,
        speech_model="phone_call",
        language=settings.LANGUAGE,
    )

