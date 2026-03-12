"""
utils.py — Shared helpers for the voice assistance module.

Sections:
  1. State management
  2. LLM helpers
  3. LLM streaming helpers
  4. Conversation helpers
  5. Appointment-type catalogue helpers
  6. Identity helpers
  7. Twilio helpers
  8. Date / time helpers
  9. Slot helpers
 10. Intent detection
"""

from __future__ import annotations

import json
import re
from datetime import date, time
from typing import Any, Dict, List, Optional, Tuple

from twilio.twiml.voice_response import Gather, Say

from src.config.settings import settings
from src.control.voice_assistance.models import ainvoke_llm, astream_llm, get_llama1
from src.control.voice_assistance.prompts.confirmation_node_prompt import (
    CONVERSATION_PROMPT,
    VERIFIER_PROMPT,
)


# ── 1. State management ───────────────────────────────────────────────────────

def update_state(state: dict, **kwargs: Any) -> dict:
    """Return a new state dict with the given keys updated."""
    return {**state, **kwargs}


def fresh_state(
    call_to_number=None,
    call_sid=None,
    identity_user_name=None,
    identity_user_email=None,
    identity_user_phone=None,
    identity_patient_id=None,
    appointment_types=None,
) -> dict:
    """Return a blank call state pre-populated with optional caller info."""
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


# ── 2. LLM helpers ────────────────────────────────────────────────────────────

def clear_markdown(raw: str) -> str:
    """Strip leading/trailing markdown code fences from an LLM response."""
    if raw.startswith("```"):
        return "\n".join(
            line for line in raw.splitlines()
            if "```" not in line
        ).strip()
    return raw.strip()


async def is_emergency(text: str, get_llama, system_prompt: str) -> bool:
    """Return True if the LLM classifies *text* as an emergency."""
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
    """Generate the next AI message for the clarify flow."""
    topics_str = (
        "\n".join(f"- {t}" for t in uncovered_topics)
        if uncovered_topics
        else "None — all covered."
    )
    prompt = (
        f"Conversation so far:\n"
        f"{conversation if conversation.strip() else '(No conversation yet — warmly thank the patient for confirming their name and phone number, then ask about their main symptom.)'}\n\n"
        f"Topics still not covered:\n{topics_str}\n\n"
        f"Generate your next response now."
    )
    try:
        response = await model([
            ("system", system_prompt),
            ("human", prompt),
        ])
        return response.content.strip().strip('"').strip("'")
    except Exception as exc:
        print("generate_next_response error:", str(exc))
        return "Could you tell me a bit more about what brings you in today?"


# ── 3. LLM streaming helpers ──────────────────────────────────────────────────

async def collect_stream(messages: list) -> str:
    """Collect all streaming chunks from ``astream_llm`` into a single string."""
    full_content = ""
    async for token in astream_llm(messages):
        full_content += token
    return full_content


async def llm_invoke_raw(system: str, human: str) -> str:
    """
    Stream the LLM with a system+human pair and return the full plain-text reply.

    Use this when the response is free-form text (decisions, labels, etc.)
    that does NOT need JSON parsing.
    """
    chunks: list[str] = []
    async for chunk in astream_llm([("system", system), ("human", human)]):
        chunks.append(chunk)
    return "".join(chunks).strip()


async def llm_extract_json(system: str, human: str) -> dict:
    """
    Stream the LLM with a system+human pair and parse the reply as JSON.

    Strips markdown code fences before parsing.
    Returns an empty dict on any error so callers can handle missing keys safely.
    """
    try:
        raw = ""
        async for chunk in astream_llm([("system", system), ("human", human)]):
            raw += chunk
        return json.loads(clear_markdown(raw.strip()))
    except Exception as exc:
        print("[llm_extract_json] error:", exc)
        return {}


async def ainvoke_llm_text(messages: list) -> str:
    """
    Invoke the LLM (with API-key rotation) and return the reply as clean text.

    Strips surrounding whitespace and quote characters — the standard pattern
    used by every node that generates spoken/conversational AI responses.

    Use this instead of:
        llm = get_llama1()
response = await llm.ainvoke(messages)
        ai_text = response.content.strip().strip('"').strip("'")
    """
    llm = get_llama1()
    response = await llm.ainvoke(messages)
    return response.content.strip().strip('"').strip("'")


async def ainvoke_llm_json(messages: list) -> dict:
    """
    Invoke the LLM (with API-key rotation) and parse the reply as JSON.

    Strips markdown code fences before parsing.
    Returns an empty dict on any error so callers can handle missing keys safely.

    Use this instead of:
        llm = get_llama1()
response = await llm.ainvoke(messages)
        data = json.loads(clear_markdown(response.content.strip()))
    """
    try:
        llm = get_llama1()
        response = await llm.ainvoke(messages)
        return json.loads(clear_markdown(response.content.strip()))
    except Exception as exc:
        print("[ainvoke_llm_json] error:", exc)
        return {}


async def llm1_invoke_text(messages: list) -> str:
    """
    Invoke the **small/fast** Llama model (llama-3.1-8b-instant) and return clean text.

    Use this for lightweight classification tasks (coverage checks, reason extraction,
    emergency detection) where the small model is intentionally preferred over the
    larger rotated-key model used by ``ainvoke_llm_text``.

    Strips surrounding whitespace and quote characters.
    """
    response = await get_llama1().ainvoke(messages)
    return response.content.strip().strip('"').strip("'")


# ── 4. Conversation helpers ───────────────────────────────────────────────────

def build_conversation_string(history: list[dict]) -> str:
    """
    Convert a conversation history list into a readable transcript.

    Accepts both {"role": "agent"/"patient"/"user"/"assistant", "text"/"content": ...}
    formats so it works across all nodes.
    """
    role_map = {
        "agent":     "Agent",
        "assistant": "Agent",
        "user":      "Patient",
        "patient":   "Patient",
    }
    lines: list[str] = []
    for turn in history:
        role = role_map.get(turn.get("role", "").lower(), "Unknown")
        text = turn.get("content") or turn.get("text", "")
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


def build_symptoms_text(history: list[dict], topics: list[str]) -> str:
    """Pair topic questions with the patient's answers from history."""
    patient_turns = [
        t.get("text", t.get("content", ""))
        for t in history
        if t.get("role") in ("patient", "user")
    ]
    pairs = [
        f"Q: {topic.capitalize()}\nA: {patient_turns[i] if i < len(patient_turns) else 'Not provided'}"
        for i, topic in enumerate(topics)
    ]
    return "\n\n".join(pairs)


def build_history_text(conversation_history: list | str) -> str:
    """
    Render a conversation history (list of dicts or a plain string) as
    'Role: text' lines — suitable for injecting into LLM prompts.
    """
    if not isinstance(conversation_history, list):
        return str(conversation_history)

    lines: list[str] = []
    for turn in conversation_history:
        if isinstance(turn, dict):
            role = turn.get("role", "unknown").capitalize()
            text = turn.get("content", turn.get("text", ""))
        elif isinstance(turn, (list, tuple)) and len(turn) == 2:
            role, text = str(turn[0]).capitalize(), turn[1]
        else:
            continue
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


# ── 5. Appointment-type catalogue helpers ─────────────────────────────────────

def build_catalogue_lines(appointment_types: dict) -> str:
    """
    Render the appointment-type catalogue as newline-separated strings for LLM prompts.
    appointment_types format: {id: (name, description)}
    """
    return "\n".join(
        f"  id={type_id}, name={name}, description={description}"
        for type_id, (name, description) in appointment_types.items()
    )


def fallback_appointment_type(appointment_types: dict) -> tuple[int, str]:
    """
    Return (id, normalised_name) of the best fallback appointment type
    (prefers any type whose name contains 'general'; otherwise the first entry).
    """
    for type_id, (name, _) in appointment_types.items():
        if "general" in name.lower():
            return type_id, name.strip().lower().replace(" ", "_")
    first_id = next(iter(appointment_types))
    return first_id, appointment_types[first_id][0].strip().lower().replace(" ", "_")


def fallback_appointment_type_id(appointment_types: dict) -> int:
    """Return just the ID of the fallback appointment type."""
    type_id, _ = fallback_appointment_type(appointment_types)
    return type_id


# ── 6. Identity helpers ───────────────────────────────────────────────────────

async def verify_user_identity(
    user_text: str,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Ask the LLM whether the user has confirmed their identity.
    Returns (confirmed, corrected_name, corrected_phone).
    """
    verify_messages = [
        {"role": "system", "content": VERIFIER_PROMPT},
        {"role": "user", "content": f"Latest user reply: {user_text}"},
    ]
    response = await ainvoke_llm(verify_messages)
    data = json.loads(clear_markdown(response.content.strip()))
    return (
        bool(data.get("confirmed", False)),
        data.get("corrected_name"),
        data.get("corrected_phone"),
    )


def apply_corrections(
    state: Dict[str, Any],
    corrected_name: Optional[str],
    corrected_phone: Optional[str],
) -> Dict[str, Any]:
    """Apply name/phone corrections returned by the identity verifier to state."""
    if corrected_name:
        state["identity_user_name"] = corrected_name
    if corrected_phone:
        state["identity_user_phone"] = corrected_phone
    return state


# ── 7. Twilio helpers ─────────────────────────────────────────────────────────

def say(parent, text: str) -> None:
    """Append a <Say> element with SSML prosody wrapping to parent."""
    ssml = f'<speak><prosody rate="{settings.SPEAKING_RATE}">{text}</prosody></speak>'
    parent.append(Say(message=ssml, voice=settings.VOICE))


def make_gather() -> Gather:
    """Return a configured Twilio <Gather> element for speech input."""
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


# ── 8. Date / time helpers ────────────────────────────────────────────────────

MORNING_START   = time(6,  0)
MORNING_END     = time(12, 0)
AFTERNOON_START = time(12, 0)
AFTERNOON_END   = time(17, 0)
EVENING_START   = time(17, 0)
EVENING_END     = time(21, 0)


def format_time(t: time) -> str:
    """Return a human-readable 12-hour time string, e.g. '9:00 AM'."""
    return t.strftime("%I:%M %p").lstrip("0")


def format_date(d: date) -> str:
    """Return a human-readable date string, e.g. 'Monday, Jan 06 2025'."""
    return d.strftime("%A, %b %d %Y")


def format_date_iso(d: date) -> str:
    """Return 'Monday, Jan 06 2025 -> 2025-01-06' (used in LLM date-option lists)."""
    return f"{format_date(d)} -> {d.isoformat()}"


def classify_period(t: time) -> str:
    """Classify a time into 'morning', 'afternoon', 'evening', or 'night'."""
    if MORNING_START <= t < MORNING_END:
        return "morning"
    if AFTERNOON_START <= t < AFTERNOON_END:
        return "afternoon"
    if EVENING_START <= t < EVENING_END:
        return "evening"
    return "night"


# ── 9. Slot helpers ───────────────────────────────────────────────────────────

def slots_for_date(all_slots: list[dict], target: date) -> list[dict]:
    """Return only slots whose date matches target."""
    return [s for s in all_slots if s["date"] == target]


def group_slots_by_period(slots: list[dict]) -> dict[str, list[dict]]:
    """Return {period: [slot, ...]} for every slot in slots."""
    periods: dict[str, list[dict]] = {}
    for s in slots:
        periods.setdefault(s["period"], []).append(s)
    return periods


def get_available_dates(all_slots: list[dict]) -> list[date]:
    """Return unique sorted dates present in all_slots."""
    return sorted({s["date"] for s in all_slots})


def build_date_options_text(available_dates: list[date]) -> str:
    """Multi-line string of date options for LLM prompts."""
    return "\n".join(format_date_iso(d) for d in available_dates)


def build_slot_context_text(slots: list[dict], *, use_full_display: bool = False) -> str:
    """Multi-line string of slot details for LLM prompts."""
    display_key = "full_display" if use_full_display else "display"
    return "\n".join(
        f"slot_id={s['id']} start_time={s['start_time']} end_time={s['end_time']} display={s[display_key]}"
        for s in slots
    )


def _coerce_time(val: time | str | None) -> time | None:
    if val is None:
        return None
    if isinstance(val, time):
        return val
    try:
        return time.fromisoformat(str(val))
    except Exception:
        return None


def exclude_previously_selected_slot(
    slots: list[dict],
    user_change_request: str | None,
    prev_start: str | None,
    prev_end: str | None,
) -> list[dict]:
    """
    When the user wants to change their slot, remove the slot they already
    had so it won't be offered again. Falls back to the original list if
    filtering would leave nothing.
    """
    if not user_change_request or not prev_start or not prev_end:
        return slots

    prev_start_t = _coerce_time(prev_start)
    prev_end_t   = _coerce_time(prev_end)

    if prev_start_t is None or prev_end_t is None:
        return slots

    filtered = [
        s for s in slots
        if not (
            _coerce_time(s["start_time"]) == prev_start_t
            and _coerce_time(s["end_time"]) == prev_end_t
        )
    ]
    return filtered or slots


def get_nearest_alternate_dates(chosen_date: date, available_dates: list[date]) -> list[date]:
    """
    Return up to 3 dates nearest to chosen_date (1 before + 2 after when
    possible) from available_dates, sorted ascending.
    """
    before = sorted([d for d in available_dates if d < chosen_date], reverse=True)
    after  = sorted([d for d in available_dates if d > chosen_date])

    alts: list[date] = []
    if before:
        alts.append(before[0])
    alts.extend(after[:2])

    if len(alts) < 3:
        if not before and len(after) >= 3:
            alts = after[:3]
        elif not after and len(before) >= 3:
            alts = sorted(before[:3])

    return sorted(set(alts))[:3]


# ── 10. Intent detection ──────────────────────────────────────────────────────

_SLOT_CHOICE_RE = re.compile(
    r"\b(\d{1,2}(:\d{2})?\s*(am|pm)?"
    r"|morning|afternoon|evening|night"
    r"|first|second|last|other|another)\b",
    re.IGNORECASE,
)


def looks_like_slot_choice(text: str) -> bool:
    """
    Heuristic: does the user's utterance look like they're picking a time
    slot rather than issuing a different command?
    """
    return bool(_SLOT_CHOICE_RE.search(text))
