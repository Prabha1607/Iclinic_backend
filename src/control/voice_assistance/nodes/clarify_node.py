import asyncio
import json
from src.control.voice_assistance.models import astream_llm, get_llama1
from src.control.voice_assistance.prompts.clarify_node_prompt import (
    CLARIFY_SYSTEM_PROMPT,
    COVERAGE_CHECK_SYSTEM_PROMPT,
    COVERAGE_CHECK_HUMAN_TEMPLATE,
    EMERGENCY_SYSTEM_PROMPT,
    EMERGENCY_RESPONSE,
    FALLBACK_RESPONSE,
    TOPICS,
)
from src.control.voice_assistance.prompts.mapping_node_prompt import (
    SYSTEM_PROMPT as MAPPING_SYSTEM_PROMPT,
    CLASSIFIER_SYSTEM_PROMPT,
    DEFAULT_INTENT,
)
from src.control.voice_assistance.utils import (
    is_emergency,
    update_state,
    clear_markdown,
)


_REASON_SYSTEM_PROMPT = """
You are a medical intake assistant.
Read the conversation and write a short, clear reason for the patient's visit in plain English.
- 1–2 sentences max.
- Write it as a clinical note, e.g. "Patient reports persistent lower back pain for 3 days with no prior injury."
- Do NOT include patient name, appointment type, or any JSON — just the plain reason text.
""".strip()


def _normalise(text: str) -> str:
    return text.strip().lower().replace(" ", "_").replace("-", "_")


def _build_catalogue_lines(appointment_types: dict) -> str:
    return "\n".join(
        f"  id={type_id}, name={name}, description={description}"
        for type_id, (name, description) in appointment_types.items()
    )


def _build_conversation_string(history: list[dict]) -> str:
    role_map = {"user": "Patient", "assistant": "Agent"}
    return "\n".join(
        f"{role_map.get(turn['role'], turn['role'].capitalize())}: {turn['content']}"
        for turn in history
    )


def _fallback_type(appointment_types: dict) -> tuple[int, str]:
    if not appointment_types:
        return -1, DEFAULT_INTENT
    for type_id, (name, _) in appointment_types.items():
        if "general" in name.lower():
            return type_id, _normalise(name)
    first_id = next(iter(appointment_types))
    return first_id, _normalise(appointment_types[first_id][0])


async def _classify_intent(conversation_str: str, appointment_types: dict) -> str:
    catalogue = _build_catalogue_lines(appointment_types)
    prompt = f"""Appointment type catalogue:
{catalogue}

Full intake conversation:
{conversation_str}

Based on the full conversation above, classify the patient into the most appropriate appointment type.
Return JSON with key "intent" only."""

    try:
        llm = get_llama1()
        response = await llm.ainvoke([
            ("system", MAPPING_SYSTEM_PROMPT),
            ("human", prompt),
        ])
        clean = clear_markdown(response.content.strip())
        parsed = json.loads(clean)
        intent = str(parsed.get("intent", DEFAULT_INTENT)).strip().lower()
    except Exception as e:
        print("[_classify_intent error]:", e)
        return DEFAULT_INTENT

    valid_intents = [_normalise(name) for _, (name, _) in appointment_types.items()]
    return intent if intent in valid_intents else DEFAULT_INTENT


async def _resolve_appointment_type_id(intent: str, appointment_types: dict) -> int:
    catalogue = _build_catalogue_lines(appointment_types)
    prompt = f"""Given the following appointment type catalogue:
{catalogue}

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
        raw_id = parsed.get("appointment_type_id")
        if raw_id is None:
            raise ValueError("null appointment_type_id in LLM response")
        return int(raw_id)
    except Exception as e:
        print("[_resolve_appointment_type_id error]:", e)
        fallback_id, _ = _fallback_type(appointment_types)
        return fallback_id


async def _extract_reason(conversation_str: str) -> str:
    try:
        llm = get_llama1()
        response = await llm.ainvoke([
            ("system", _REASON_SYSTEM_PROMPT),
            ("human", f"Conversation:\n{conversation_str}"),
        ])
        return response.content.strip().strip('"').strip("'")
    except Exception as e:
        print("[_extract_reason error]:", e)
        return ""


async def _run_mapping(conversation_str: str, appointment_types: dict) -> tuple[int, str, str]:
    try:
        intent, reason_for_visit = await asyncio.wait_for(
            asyncio.gather(
                _classify_intent(conversation_str, appointment_types),
                _extract_reason(conversation_str),
            ),
            timeout=5.0,
        )
        appointment_type_id = await asyncio.wait_for(
            _resolve_appointment_type_id(intent, appointment_types),
            timeout=3.0,
        )
        print("[mapping] intent:", intent, "| type_id:", appointment_type_id)
        print("[mapping] reason:", reason_for_visit)
        return appointment_type_id, intent, reason_for_visit
    except asyncio.TimeoutError:
        print("[mapping] timed out — using fallback")
    except Exception as e:
        print("[mapping error]:", e)

    fallback_id, fallback_intent = _fallback_type(appointment_types)
    return fallback_id, fallback_intent, ""


async def _collect(messages: list) -> str:
    full_content = ""
    async for token in astream_llm(messages):
        full_content += token
    return full_content


async def get_covered_topics(history: list[dict], topics: list[str]) -> list[str]:
    unchecked_numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics))
    conversation = _build_conversation_string(history)

    prompt = COVERAGE_CHECK_HUMAN_TEMPLATE.format(
        conversation=conversation,
        topics_numbered=unchecked_numbered,
    )

    try:
        model = get_llama1()
        response = await model.ainvoke([
            ("system", COVERAGE_CHECK_SYSTEM_PROMPT),
            ("human", prompt),
        ])

        raw = response.content.strip().upper()
        print("[coverage_check raw]:", raw)

        if not raw or raw == "NONE":
            return []

        return [
            topics[int(n.strip()) - 1]
            for n in raw.split(",")
            if n.strip().isdigit() and 0 <= int(n.strip()) - 1 < len(topics)
        ]

    except Exception as exc:
        print("[get_covered_topics error]:", exc)
        return []


def _build_greeting(user_name: str | None) -> str:
    name_part = f", {user_name}" if user_name else ""
    return f"Hi{name_part}! Thanks for confirming — I just need to ask you a few quick questions before we get you booked in. "


async def _refresh_covered_topics(history: list[dict], covered: list[str]) -> list[str]:
    unchecked = [t for t in TOPICS if t not in covered]
    if not unchecked:
        return covered

    newly_covered = await get_covered_topics(history, unchecked)

    result = list(covered)
    for t in TOPICS:
        if t in newly_covered and t not in result:
            result.append(t)
    return result


def _build_clarify_messages(history: list[dict], uncovered: list[str]) -> list[dict]:
    seed = history if history else [{"role": "user", "content": "start"}]
    return [
        {
            "role": "system",
            "content": CLARIFY_SYSTEM_PROMPT.format(
                next_topic=uncovered[0],
                remaining_count=len(uncovered),
            ),
        },
        *seed,
    ]


def _is_clarify_active(history: list[dict]) -> bool:
    return any(turn.get("role") == "assistant" for turn in history)


async def clarify_node(state: dict) -> dict:
    print("[clarify_node] -----------------------------")
    try:
        history: list[dict] = list(state.get("clarify_conversation_history") or [])
        user_text: str | None = state.get("speech_user_text")
        covered: list[str] = list(state.get("clarify_covered_topics") or [])
        user_name: str | None = state.get("identity_user_name")
        appointment_types: dict = state.get("appointment_types") or {}

        print("[clarify_node] appointment_types from state:", appointment_types)

        is_first_turn = len(history) == 0

        if user_text:
            user_text = user_text.strip()
            history.append({"role": "user", "content": user_text})
            print("[user_response]:", user_text)

            clarify_has_started = _is_clarify_active(history)
            if clarify_has_started and await is_emergency(user_text, get_llama=get_llama1, system_prompt=EMERGENCY_SYSTEM_PROMPT):
                return update_state(
                    state,
                    speech_ai_text=EMERGENCY_RESPONSE,
                    mapping_emergency=True,
                    clarify_completed=True,
                    clarify_conversation_history=history,
                    clarify_covered_topics=covered,
                )

            uncovered_optimistic = [t for t in TOPICS if t not in covered]
            messages = _build_clarify_messages(history, uncovered_optimistic) if uncovered_optimistic else None

            if messages:
                covered, full_content = await asyncio.gather(
                    _refresh_covered_topics(history, covered),
                    _collect(messages),
                )
            else:
                covered = await _refresh_covered_topics(history, covered)
                full_content = ""

            print("[covered_topics]:", covered)

        else:
            full_content = ""

        uncovered = [t for t in TOPICS if t not in covered]
        print("[uncovered_topics]:", uncovered)

        if not uncovered:
            conversation_str = _build_conversation_string(history)

            if appointment_types:
                appointment_type_id, intent, reason_for_visit = await _run_mapping(
                    conversation_str, appointment_types
                )
            else:
                print("[clarify_node] WARNING: appointment_types is empty — cannot map. Check that appointment_types is loaded into state before clarify_node runs.")
                appointment_type_id, intent = _fallback_type(appointment_types)
                reason_for_visit = ""

            friendly_name = intent.replace("_", " ").title()
            bridge_text = (
                f"Thank you for sharing that! I'll go ahead and look into booking "
                f"a {friendly_name} appointment for you now."
            )

            return update_state(
                state,
                clarify_conversation_history=history,
                clarify_covered_topics=covered,
                clarify_completed=True,
                mapping_intent=intent,
                mapping_appointment_type_id=appointment_type_id,
                mapping_appointment_type_completed=True,
                booking_reason_for_visit=reason_for_visit,
                speech_ai_text=bridge_text,
            )

        if not full_content:
            messages = _build_clarify_messages(history, uncovered)
            full_content = await _collect(messages)

        ai_text = full_content.strip().strip('"').strip("'")
        print("[ai_response]:", ai_text)

        if is_first_turn:
            ai_text = _build_greeting(user_name) + ai_text

        history.append({"role": "assistant", "content": ai_text})

        return update_state(
            state,
            speech_ai_text=ai_text,
            clarify_conversation_history=history,
            clarify_covered_topics=covered,
            clarify_completed=False,
        )

    except Exception as exc:
        print("[clarify_node error]:", exc)
        return update_state(
            state,
            speech_ai_text=FALLBACK_RESPONSE,
            clarify_completed=True,
            speech_error=str(exc),
        )