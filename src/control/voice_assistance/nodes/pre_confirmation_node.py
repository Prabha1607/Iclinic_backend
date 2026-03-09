import json
from src.control.voice_assistance.models import get_llama1
from src.control.voice_assistance.utils import clear_markdown, update_state



PRE_CONFIRMATION_SYSTEM_PROMPT = """
You are a warm, professional medical receptionist confirming an appointment over the phone.

You will receive a JSON snapshot of the booking details.
Your job is to read back the appointment naturally — the way a real receptionist would speak, not like a system listing fields.

Guidelines:
- Address the patient by their first name only (not full name)
- Weave the details into natural flowing speech — do NOT list them one by one
- Mention the doctor with "Dr." prefix, the day and time conversationally (e.g. "this Tuesday at two in the afternoon")
- If a reason or symptom is present, acknowledge it briefly and empathetically (e.g. "I can see you're coming in about a high fever")
- Close with a warm, simple confirmation question — something like "Does that all sound right?" or "Shall I go ahead and lock that in for you?"
- If a field is missing, skip it without drawing attention to it

Tone: friendly, calm, human — like a real person on the phone, not a robot reading a form.
Length: 2–3 natural sentences maximum.

Return ONLY the spoken message. No JSON, no markdown, no extra commentary.
""".strip()

INTENT_DETECTION_SYSTEM_PROMPT = """
You are analysing a patient's spoken reply to a booking confirmation question.

Respond with a single JSON object:
{
  "confirmed": true | false,
  "uncertain": true | false
}

Rules:
- confirmed = true  → patient clearly said yes / correct / confirmed / go ahead / 
                       sounds good / book it / okay / alright / sure / yep / 
                       "go ahead" or phonetic approximations like "gohe", "go ed", "go hed"
- confirmed = false → patient EXPLICITLY said no / cancel / wrong / stop / 
                       do not book / don't book / change it
- uncertain = true  → ANYTHING that is not a clear yes or clear no:
                       - garbled or unrecognisable words
                       - short ambiguous fragments
                       - unrelated statements
                       - slang or heavily accented approximations of "yes"
                       Set confirmed = false when uncertain = true.

When in doubt, ALWAYS prefer uncertain = true over confirmed = false.
A false negative (missing a "yes") is far more costly than asking again.

Return ONLY the JSON object, nothing else.
""".strip()


def _build_snapshot(state: dict) -> dict:
    slot = state.get("slot_selected") or {}
    return {
        "patient_name":    state.get("identity_user_name"),
        "doctor_name":     state.get("doctor_confirmed_name"),
        "appointment_slot": slot.get("full_display") or state.get("slot_booked_display"),
        "appointment_date": slot.get("date"),
        "appointment_time": f"{slot.get('start_time')} – {slot.get('end_time')}"
                            if slot.get("start_time") else None,
        "appointment_type_id": state.get("mapping_appointment_type_id"),
        "symptoms_summary": state.get("clarify_symptoms_text"),
        "reason_for_visit": state.get("booking_reason_for_visit"),
    }


async def _generate_confirmation_message(snapshot: dict) -> str:
    llm = get_llama1()
    response = await llm.ainvoke([
        ("system", PRE_CONFIRMATION_SYSTEM_PROMPT),
        ("human", f"Booking details:\n{json.dumps(snapshot, default=str, indent=2)}")
    ])
    return response.content.strip()


async def _detect_user_intent(user_text: str) -> tuple[bool, bool]:
    llm = get_llama1()
    try:
        response = await llm.ainvoke([
            ("system", INTENT_DETECTION_SYSTEM_PROMPT),
            ("human", f"Patient reply: \"{user_text}\"")
        ])
        parsed = json.loads(clear_markdown(response.content.strip()))
        return bool(parsed.get("confirmed")), bool(parsed.get("uncertain"))
    except Exception:
        return False, True



async def pre_confirmation_node(state: dict) -> dict:

    awaiting = state.get("booking_awaiting_confirmation", False)

    if awaiting:
        user_text = (state.get("speech_user_text") or "").strip()
        print(f"[pre_confirmation_node] User reply: {user_text!r}")

        confirmed, uncertain = await _detect_user_intent(user_text)

        if confirmed:
            print("[pre_confirmation_node] User confirmed — proceeding to book")
            return update_state(
                state,
                booking_awaiting_confirmation=False,
                pre_confirmation_completed=True,
                pre_confirmation_retry_count=0,
                speech_ai_text=None,
            )

        if uncertain:
            retry_count = state.get("pre_confirmation_retry_count", 0) + 1
            print(f"[pre_confirmation_node] Uncertain reply (attempt {retry_count})")

            if retry_count >= 3:
                print("[pre_confirmation_node] Too many uncertain replies — cancelling")
                return update_state(
                    state,
                    booking_awaiting_confirmation=False,
                    pre_confirmation_completed=False,
                    pre_confirmation_retry_count=0,
                    slot_selected=None,
                    slot_stage="selecting",
                    slot_selection_completed=False,
                    speech_ai_text=(
                        "I'm having a little trouble hearing you clearly. "
                        "Let me take you back to the slot selection so we can start fresh."
                    ),
                )

            snapshot = state.get("booking_context_snapshot") or _build_snapshot(state)
            re_ask = (
                "I didn't quite catch that — could you say yes or no? "
                + await _generate_confirmation_message(snapshot)
            )
            return update_state(
                state,
                booking_awaiting_confirmation=True,
                pre_confirmation_completed=False,
                pre_confirmation_retry_count=retry_count,
                speech_ai_text=re_ask,
            )

        print("[pre_confirmation_node] User rejected — returning to slot selection")
        return update_state(
            state,
            booking_awaiting_confirmation=False,
            pre_confirmation_completed=False,
            pre_confirmation_retry_count=0,
            slot_selected=None,
            slot_stage="selecting",
            slot_selection_completed=False,
            speech_ai_text=(
                "No problem! Let me show you the available slots again "
                "so you can pick a different time."
            ),
        )

    print("[pre_confirmation_node] First call — generating confirmation message")
    snapshot = _build_snapshot(state)
    print(f"[pre_confirmation_node] Snapshot: {json.dumps(snapshot, default=str)}")

    try:
        confirmation_text = await _generate_confirmation_message(snapshot)
    except Exception as e:
        print(f"[pre_confirmation_node] LLM error: {e}")
        slot = state.get("slot_selected") or {}
        confirmation_text = (
            f"I'd like to confirm your appointment with "
            f"{state.get('doctor_confirmed_name', 'the doctor')} "
            f"on {slot.get('full_display', 'the selected slot')}. "
            "Shall I go ahead and book this for you? Please say yes or no."
        )

    return update_state(
        state,
        booking_awaiting_confirmation=True,
        pre_confirmation_completed=False,
        pre_confirmation_retry_count=0,
        booking_context_snapshot=snapshot,
        speech_ai_text=confirmation_text,
    )

