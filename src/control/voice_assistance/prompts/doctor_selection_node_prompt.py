NO_DOCTORS_RESPONSE = "I'm sorry, no doctors are currently available. Please try again later."

DOCTOR_MATCH_SYSTEM_PROMPT = (
    "You are a medical scheduling assistant. "
    "Match the user's response to the correct doctor from the list. "
    'Reply ONLY with valid JSON: {"doctor_id": <int>, "doctor_name": "<string>"} '
    "If unclear, pick the doctor whose specialization best fits the patient intent."
)
