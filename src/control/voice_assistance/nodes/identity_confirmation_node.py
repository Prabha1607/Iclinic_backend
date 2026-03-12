import asyncio
from typing import Dict, Any
from src.control.voice_assistance.models import astream_llm
from src.control.voice_assistance.prompts.confirmation_node_prompt import CONVERSATION_PROMPT
from src.control.voice_assistance.utils import apply_corrections, verify_user_identity


async def _collect(messages: list) -> str:
    full_content = ""
    async for token in astream_llm(messages):
        full_content += token
    return full_content


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

        confirmed = False
        corrected_name = None
        corrected_phone = None

        if user_text:
            full_content, verify_result = await asyncio.gather(
                _collect(messages),
                verify_user_identity(user_text),
            )
            try:
                confirmed, corrected_name, corrected_phone = verify_result
            except Exception as e:
                print("[VERIFIER ERROR]", e)
        else:
            full_content = await _collect(messages)

        sentence = full_content.strip()

    except Exception as e:
        print("[LLM ERROR]", e)
        return state

    state = apply_corrections(state, corrected_name, corrected_phone)
    conversation_history.append({"role": "assistant", "content": sentence})

    return {
        **state,
        "clarify_conversation_history": conversation_history,
        "identity_confirmed_user": confirmed,
        "identity_confirmation_completed": confirmed,
        "speech_ai_text": sentence,
    }

