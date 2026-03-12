import json
from typing import Any
from src.control.voice_assistance.prompts.stt_node_prompt import STT_INTENT_SYSTEM
from src.control.voice_assistance.models import get_llama1
from src.control.voice_assistance.utils import clear_markdown


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


import time

async def stt_node(state: dict) -> dict:
    start_time = time.time()
    print(f"[stt_node] start_time: {start_time:.4f}")

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
        "pipeline_start_time":          start_time,
    }

    intent = await _detect_change_intent(cleaned)

    if intent == "change_doctor" and state.get("doctor_confirmed_id") is not None:
        return _reset_from_doctor(base_state, cleaned)

    if intent == "change_date" and state.get("slot_chosen_date") is not None:
        return _reset_from_date(base_state, cleaned)

    if intent == "change_slot" and state.get("slot_selected") is not None:
        return _reset_from_slot(base_state, cleaned)

    return base_state

