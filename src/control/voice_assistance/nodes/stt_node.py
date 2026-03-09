import json
from typing import Any
from src.control.voice_assistance.models import get_llama1
from src.control.voice_assistance.utils import clear_markdown

STT_INTENT_SYSTEM = """
You are an intent classifier for a medical appointment voice booking system.

The user is mid-flow — they may have already selected a doctor, date, time period, or slot.
Your job is to detect if the user wants to CHANGE a previously selected item.

Classify the user's message into ONE of these intents:
- "change_doctor"    → user wants to pick a different doctor
- "change_date"      → user wants to pick a different appointment date  
- "change_slot"      → user wants to pick a different appointment time slot
- "none"             → anything else (normal response, confirmation, unrelated)

Rules:
- Only return "change_doctor" / "change_date" / "change_period" / "change_slot" if the user is EXPLICITLY asking to change something already chosen.
- Phrases like "actually I want a different doctor", "can I change the date", "I'd prefer a different time of day", "switch doctors" → change intents.
- Phrases like "can I pick a different time", "I want a different slot", "change the appointment time" → "change_slot".
- A user just saying a doctor name, date, or time for the first time is NOT a change intent → return "none".
- When in doubt, return "none".

Respond with ONLY valid JSON, no markdown, no explanation:
{"intent": "<change_doctor|change_date|change_period|change_slot|none>"}
""".strip()


def _reset_from_doctor(state: dict, user_text: str) -> dict:
    return {
        **state,
        "user_change_request":        user_text,
        "doctor_selection_pending":   False,
        "doctor_selection_completed": False,
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
        "booking_appointment_completed": False,
        "booking_reason_for_visit":      None,
        "booking_notes":                 None,
        "booking_instructions":          None,
        "booking_awaiting_confirmation": False,
        "booking_context_snapshot":      None,   
        "pre_confirmation_completed":    False,  
        "cancellation_stage":       None,
        "cancellation_appointment": None,
        "cancellation_complete":    False,
    }


def _reset_from_date(state: dict, user_text: str) -> dict:
    return {
        **state,
        "user_change_request":      user_text,
        "slot_stage":               None,
        "slot_selection_completed": False,
        "slot_chosen_period":       None,
        "slot_available_list":      None,
        "slot_selected":            None,
        "slot_selected_start_time": None,
        "slot_selected_end_time":   None,
        "slot_selected_display":    None,
        "slot_booked_id":           None,
        "slot_booked_display":      None,
        "booking_appointment_completed": False,
        "booking_reason_for_visit":      None,
        "booking_notes":                 None,
        "booking_instructions":          None,
        "booking_awaiting_confirmation": False,
        "booking_context_snapshot":      None,   
        "pre_confirmation_completed":    False,  
        "cancellation_stage":       None,
        "cancellation_appointment": None,
        "cancellation_complete":    False,
    }


def _reset_from_slot(state: dict, user_text: str) -> dict:
    return {
        **state,
        "user_change_request":           user_text,   
        "slot_stage":                    "ask_slot",  
        "slot_selection_completed":      False,
        "slot_selected":                 None,        
        "slot_selected_display":         None,
        "slot_booked_id":                None,
        "slot_booked_display":           None,
        "booking_appointment_completed": False,
        "booking_reason_for_visit":      None,
        "booking_notes":                 None,
        "booking_instructions":          None,
        "booking_awaiting_confirmation": False,
        "booking_context_snapshot":      None,   
        "pre_confirmation_completed":    False,  
        "cancellation_stage":            None,
        "cancellation_appointment":      None,
        "cancellation_complete":         False,
    }


async def _detect_change_intent(user_text: str) -> str:
    try:
        llm = get_llama1()
        response = await llm.ainvoke([
            ("system", STT_INTENT_SYSTEM),
            ("human", user_text),
        ])
        raw = response.content.strip()
        parsed = json.loads(clear_markdown(raw))
        return parsed.get("intent", "none")
    except Exception as e:
        print(f"[stt_node] intent detection failed: {e}")
        return "none"


async def stt_node(state: dict) -> dict:

    user_text: str | None = state.get("speech_user_text")

    if not user_text:
        return {**state, "speech_user_text": None}
    cleaned = " ".join(user_text.split()).strip()
    
    print(f"[stt_node] user text: {user_text}")

    history = list(state.get("clarify_conversation_history") or [])
    history.append({"role": "user", "content": cleaned})

    base_state = {
        **state,
        "speech_user_text":             cleaned,
        "clarify_conversation_history": history,
        "user_change_request":          None,
    }

    intent = await _detect_change_intent(cleaned)
    print(f"[stt_node] detected intent: {intent}")

    if intent == "change_doctor" and state.get("doctor_confirmed_id") is not None:
        print("[stt_node] resetting doctor + downstream state")
        return _reset_from_doctor(base_state, cleaned)

    if intent == "change_date" and state.get("slot_chosen_date") is not None:
        print("[stt_node] resetting date + downstream state")
        return _reset_from_date(base_state, cleaned)

    if intent == "change_slot" and state.get("slot_selected") is not None:
        print("[stt_node] resetting slot + downstream state")
        return _reset_from_slot(base_state, cleaned)

    return base_state


    