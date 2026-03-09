from typing import Optional, List, Dict
from typing_extensions import TypedDict


class VoiceState(TypedDict):

    call_to_number:   Optional[str]
    call_sid:         Optional[str]
    call_user_token:  Optional[str]

    speech_user_text:   Optional[str]
    speech_ai_text:     Optional[str]
    speech_error:       Optional[str]

    service_type: Optional[str]

    identity_user_name:   Optional[str]
    identity_user_email:  Optional[str]
    identity_user_phone:  Optional[str]
    identity_patient_id:  Optional[int]

    identity_confirmation_completed: Optional[bool]
    identity_confirmed_user:         Optional[bool]
    identity_confirm_stage:          Optional[str]
    identity_speak_final:            Optional[bool]
    identity_phone_verified:         Optional[bool]

    clarify_step:                 Optional[int]
    clarify_conversation_history: Optional[List[Dict[str, str]]]
    clarify_covered_topics:       Optional[List[str]]
    clarify_completed:            Optional[bool]
    clarify_symptoms_text:        Optional[str]

    mapping_intent:                     Optional[str]
    mapping_emergency:                  Optional[bool]
    mapping_appointment_type_completed: Optional[bool]
    mapping_appointment_type_id:        Optional[int]

    appointment_types:   Optional[Dict[int, List[str]]]
    appointments_list:   Optional[List[Dict]]

    doctor_list:                Optional[List[Dict]]
    doctor_selection_pending:   Optional[bool]
    doctor_selection_completed: Optional[bool]
    doctor_confirmed_id:        Optional[int]
    doctor_confirmed_name:      Optional[str]

    slot_stage:               Optional[str]
    slot_selection_completed: Optional[bool]
    slot_chosen_date:         Optional[str]
    slot_chosen_period:       Optional[str]
    slot_available_list:      Optional[List[Dict]]
    slot_selected:            Optional[Dict]
    slot_selected_start_time: Optional[str]
    slot_selected_end_time:   Optional[str]
    slot_selected_display:    Optional[str]
    slot_booked_id:           Optional[int]
    slot_booked_display:      Optional[str]

    pre_confirmation_completed:    Optional[bool]

    booking_appointment_completed:  Optional[bool]
    booking_reason_for_visit:       Optional[str]
    booking_notes:                  Optional[str]
    booking_instructions:           Optional[str]
    booking_awaiting_confirmation:  Optional[bool]
    booking_context_snapshot:       Optional[Dict]

    cancellation_stage:       Optional[str]
    cancellation_appointment: Optional[Dict]
    cancellation_complete:    Optional[bool]

    user_change_request: Optional[str]