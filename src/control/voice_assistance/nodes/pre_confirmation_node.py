import json
from src.control.voice_assistance.prompts.pre_confirmation_node_prompt import INTENT_DETECTION_SYSTEM_PROMPT, PRE_CONFIRMATION_SYSTEM_PROMPT
from src.control.voice_assistance.models import get_llama1
from src.control.voice_assistance.utils import clear_markdown, update_state




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
            confirmation_msg = await _generate_confirmation_message(snapshot)
            re_ask = f"Sorry, I didn't quite catch that. {confirmation_msg}"
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
