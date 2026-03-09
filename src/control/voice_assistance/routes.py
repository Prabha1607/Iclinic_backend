def route_after_stt(state: dict) -> str:

    if not state.get("service_type"):
        return "service_intent"

    if state.get("service_type") == "booking":
        if not state.get("identity_confirmation_completed"):
            return "identity_confirmation"
        if not state.get("clarify_completed"):
            return "clarify"
        if not state.get("mapping_appointment_type_completed"):
            return "mapping"
        if not state.get("doctor_selection_completed"):
            return "doctor_selection"
        if not state.get("slot_selection_completed"):
            return "slot_selection"
        if not state.get("pre_confirmation_completed"):
            return "pre_confirmation"
        if not state.get("booking_appointment_completed"):
            return "book_appointment"
        return "tts"

    if state.get("service_type") == "cancellation":
        return "cancel_appointment"

    return "service_intent"


def route_after_pre_confirmation(state: dict) -> str:
    """
    Called after pre_confirmation_node runs.

    - pre_confirmation_completed = True  → user confirmed, proceed to book
    - booking_awaiting_confirmation = True → still waiting for reply, go to tts
    - neither                            → user rejected / slot reset, go to tts
                                          (slot_selection_completed was set False
                                           so next STT turn re-enters slot_selection)
    """
    if state.get("pre_confirmation_completed"):
        return "book_appointment"
    return "tts"



def route_after_identity_confirmation(state: dict) -> str:

    if not state.get("identity_confirmation_completed"):
        return "tts"
    if not state.get("identity_confirmed_user"):
        return "tts"
    if state.get("identity_speak_final"):
        return "tts"
    return "clarify"


def route_after_service_intent(state: dict) -> str:

    service = state.get("service_type")

    if service == "booking":
        return "identity_confirmation"

    if service == "cancellation":
        return "cancel_appointment"

    return "tts"


def route_after_clarify(state: dict) -> str:

    if state.get("mapping_emergency"):
        return "tts"
    if not state.get("clarify_completed"):
        return "tts"
    return "mapping"


def route_after_doctor_selection(state: dict) -> str:

    if state.get("doctor_selection_completed") and state.get("doctor_confirmed_id"):
        return "slot_selection"
    return "tts"


def route_after_slot_selection(state: dict) -> str:
    
    if state.get("slot_selection_completed") and state.get("slot_stage") == "ready_to_book":
        return "pre_confirmation"     
    return "tts"