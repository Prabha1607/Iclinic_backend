from src.control.voice_assistance.models import get_llama1
from src.control.voice_assistance.prompts.service_intent_node_prompt import SERVICE_INTENT_PROMPT

async def service_intent_node(state: dict) -> dict:
    
    user_text = state.get("speech_user_text")

    if not user_text:
        return {
            **state,
            "speech_ai_text": "Hi there! This is Front desk Assistance calling from iClinic. We noticed an appointment request come in through our website. How can I help you today? Would you like to book an appointment or cancel an appointment?",
            "service_type": None,
        }

    try:
        model = get_llama1()

        response = await model.ainvoke([
            ("system", SERVICE_INTENT_PROMPT),
            ("human", user_text),
        ])

        service = response.content.strip().lower()

        if service not in ["booking", "cancellation"]:
            return {
                **state,
                "speech_ai_text": "Sorry, I did not understand. Do you want to book an appointment or cancel one?",
                "service_type": None,
            }

        patient_id = state.get("identity_patient_id")

        return {
            **state,
            "identity_patient_id": patient_id,
            "service_type": service,
            "speech_ai_text": None,
        }
        
    except Exception as e:
        return {
            **state,
            "speech_ai_text": "Something went wrong. Please try again.",
            "speech_error": str(e),
        }