import json
from src.control.voice_assistance.utils import clear_markdown, update_state
from src.control.voice_assistance.prompts.mapping_node_prompt import SYSTEM_PROMPT, EMERGENCY_RESPONSE, CLASSIFIER_SYSTEM_PROMPT, DEFAULT_INTENT
from src.control.voice_assistance.models import get_llama1


def _normalise(text: str) -> str:
    return text.strip().lower().replace(" ", "_").replace("-", "_")


def _build_catalogue_lines(appointment_types: dict) -> str:
    return "\n".join(
        f"  id={type_id}, name={name}, description={description}"
        for type_id, (name, description) in appointment_types.items()
    )


def _build_conversation_transcript(conversation_history: list[dict]) -> str:
    lines = []
    for turn in conversation_history:
        role = "Assistant" if turn.get("role") == "assistant" else "Patient"
        content = turn.get("content", "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines).strip()


def _fallback_appointment_type_id(appointment_types: dict) -> int:
    for type_id, (name, _) in appointment_types.items():
        if "general" in name.lower():
            return type_id
    return next(iter(appointment_types))


async def _resolve_appointment_type_id(intent: str, appointment_types: dict) -> int | None:
    prompt = f"""Given the following appointment type catalogue:
{_build_catalogue_lines(appointment_types)}

The patient has been classified with intent: "{intent}"

Return ONLY a JSON object with the single key "appointment_type_id" containing the integer ID 
that best matches the intent. If nothing matches, use the ID for general check-up.

Example: {{"appointment_type_id": 3}}"""

    try:
        llm = get_llama1()
        response = await llm.ainvoke([
            ("system", CLASSIFIER_SYSTEM_PROMPT),
            ("human", prompt),
        ])
        clean = clear_markdown(response.content.strip())
        parsed = json.loads(clean)
        return int(parsed.get("appointment_type_id"))

    except (json.JSONDecodeError, TypeError, ValueError):
        return _fallback_appointment_type_id(appointment_types)
    except Exception as e:

        return _fallback_appointment_type_id(appointment_types)


async def _classify_intent(conversation_transcript: str, appointment_types: dict) -> str:
    prompt = f"""Appointment type catalogue:
{_build_catalogue_lines(appointment_types)}

Full intake conversation:
{conversation_transcript}

Based on the full conversation above, classify the patient into the most appropriate appointment type.
Return JSON with key "intent" only."""

    try:
        llm = get_llama1()
        response = await llm.ainvoke([
            ("system", SYSTEM_PROMPT),
            ("human", prompt),
        ])
        clean = clear_markdown(response.content.strip())
        parsed = json.loads(clean)
        intent = str(parsed.get("intent", DEFAULT_INTENT)).strip().lower()
    except (json.JSONDecodeError, AttributeError, KeyError):
        return DEFAULT_INTENT
    except Exception as e:

        return DEFAULT_INTENT

    valid_intents = [_normalise(name) for _, (name, _) in appointment_types.items()]
    return intent if intent in valid_intents else DEFAULT_INTENT


async def mapping_node(state: dict) -> dict:
    print("[mapping_node] -----------------------------")

    if state.get("mapping_emergency"):
        return update_state(
            state,
            mapping_intent="emergency",
            mapping_appointment_type_id=None,
            mapping_appointment_type_completed=True,
            speech_ai_text=EMERGENCY_RESPONSE,
        )

    appointment_types: dict = state.get("appointment_types") or {}

    conversation_history: list[dict] = list(state.get("clarify_conversation_history") or [])
    conversation_transcript = _build_conversation_transcript(conversation_history)

    try:
        intent = DEFAULT_INTENT if not conversation_transcript else await _classify_intent(conversation_transcript, appointment_types)
        appointment_type_id = await _resolve_appointment_type_id(intent, appointment_types)
    except Exception as e:

        intent = DEFAULT_INTENT
        appointment_type_id = _fallback_appointment_type_id(appointment_types) if appointment_types else None


    friendly_name = intent.replace("_", " ").title()

    return update_state(
        state,
        mapping_intent=intent,
        mapping_appointment_type_id=appointment_type_id,
        appointment_types=appointment_types,
        mapping_appointment_type_completed=True,
        speech_ai_text=(
            f"Based on what you've described, I'll book a {friendly_name} appointment for you. "
            f"You'll receive a confirmation shortly."
        ),
    )