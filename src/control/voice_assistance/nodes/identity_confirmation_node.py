from typing import Dict, Any
from src.control.voice_assistance.utils import apply_corrections, generate_conversation_response, prepare_conversation_history, verify_user_identity

async def identity_confirmation_node(state: Dict[str, Any]) -> Dict[str, Any]:

    print("[identity_confirmation_node] -----------------------------")

    patient_name: str = (state.get("identity_user_name") or "").strip()
    phone_number: str = (state.get("identity_user_phone") or "").strip()
    user_text: str = (state.get("speech_user_text") or "").strip()

    if not patient_name:
        return state

    conversation_history = prepare_conversation_history(state, user_text)

    try:
        sentence = await generate_conversation_response(
            patient_name, phone_number, user_text
        )
    except Exception:
        return state

    confirmed = False
    end_call = False
    corrected_name = None
    corrected_phone = None

    if user_text:
        try:
            (
                confirmed,
                end_call,
                corrected_name,
                corrected_phone,
            ) = await verify_user_identity(user_text)
        except Exception as e:
            print("[VERIFIER ERROR]", e)

    state = apply_corrections(state, corrected_name, corrected_phone)

    conversation_history.append(
        {"role": "assistant", "content": sentence}
    )

    return {
        **state,
        "clarify_conversation_history": conversation_history,
        "identity_confirmed_user": confirmed,
        "identity_confirmation_completed": confirmed or end_call,
        "speech_ai_text": sentence,
    }