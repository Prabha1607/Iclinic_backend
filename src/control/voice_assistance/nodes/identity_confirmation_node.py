from typing import Dict, Any
from src.control.voice_assistance.models import ainvoke_llm
from src.control.voice_assistance.prompts.confirmation_node_prompt import CONVERSATION_PROMPT
from src.control.voice_assistance.utils import apply_corrections, verify_user_identity


async def identity_confirmation_node(state: Dict[str, Any]) -> Dict[str, Any]:

    print("[identity_confirmation_node] -----------------------------")

    patient_name: str = (state.get("identity_user_name") or "").strip()
    phone_number: str = (state.get("identity_user_phone") or "").strip()
    user_text: str = (state.get("speech_user_text") or "").strip()
    conversation_history = list(state.get("clarify_conversation_history") or [])

    if not patient_name:
        return state

    if user_text:
        conversation_history.append({"role": "user", "content": user_text})

    try:
        history = conversation_history if conversation_history else [{"role": "user", "content": "start"}]
        messages = [
            {
                "role": "system",
                "content": CONVERSATION_PROMPT.format(
                    name=patient_name, phone=phone_number
                ),
            },
            *history,
        ]

        response = await ainvoke_llm(messages)
        sentence = response.content.strip()

    except Exception as e:
        print("[LLM ERROR]", e)
        return state

    confirmed = False
    corrected_name = None
    corrected_phone = None

    if user_text:
        try:
            confirmed, corrected_name, corrected_phone = await verify_user_identity(user_text)
        except Exception as e:
            print("[VERIFIER ERROR]", e)

    state = apply_corrections(state, corrected_name, corrected_phone)

    conversation_history.append({"role": "assistant", "content": sentence})

    return {
        **state,
        "clarify_conversation_history": conversation_history,
        "identity_confirmed_user": confirmed,
        "identity_confirmation_completed": confirmed,
        "speech_ai_text": sentence,
    }

