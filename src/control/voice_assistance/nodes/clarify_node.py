from src.control.voice_assistance.models import ainvoke_llm, get_llama1
from src.control.voice_assistance.prompts.clarify_node_prompt import (
    CLARIFY_SYSTEM_PROMPT,
    COVERAGE_CHECK_SYSTEM_PROMPT,
    COVERAGE_CHECK_HUMAN_TEMPLATE,
    EMERGENCY_SYSTEM_PROMPT,
    EMERGENCY_RESPONSE,
    FALLBACK_RESPONSE,
    TOPICS,
)
from src.control.voice_assistance.utils import (
    build_symptoms_text,
    is_emergency,
    update_state,
)


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


def _build_conversation_string(history: list[dict]) -> str:
    role_map = {"user": "Patient", "assistant": "Agent"}
    return "\n".join(
        f"{role_map.get(turn['role'], turn['role'].capitalize())}: {turn['content']}"
        for turn in history
    )


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


async def clarify_node(state: dict) -> dict:
    print("[clarify_node] -----------------------------")
    try:
        history: list[dict] = list(state.get("clarify_conversation_history") or [])
        user_text: str | None = state.get("speech_user_text")
        covered: list[str] = list(state.get("clarify_covered_topics") or [])
        user_name: str | None = state.get("identity_user_name")

        is_first_turn = len(history) == 0

        if user_text:
            user_text = user_text.strip()
            history.append({"role": "user", "content": user_text})
            print("[user_response]:", user_text)

            if await is_emergency(user_text, get_llama=get_llama1, system_prompt=EMERGENCY_SYSTEM_PROMPT):
                return update_state(
                    state,
                    speech_ai_text=EMERGENCY_RESPONSE,
                    mapping_emergency=True,
                    clarify_completed=True,
                    clarify_conversation_history=history,
                    clarify_covered_topics=covered,
                )

            covered = await _refresh_covered_topics(history, covered)
            print("[covered_topics]:", covered)

        uncovered = [t for t in TOPICS if t not in covered]
        print("[uncovered_topics]:", uncovered)

        if not uncovered:
            symptoms_text = build_symptoms_text(history, TOPICS)
            print("[symptoms_text]:", symptoms_text)
            return update_state(
                state,
                clarify_symptoms_text=symptoms_text,
                clarify_conversation_history=history,
                clarify_covered_topics=covered,
                clarify_completed=True,
                speech_ai_text=None,
            )

        seed = history if history else [{"role": "user", "content": "start"}]
        messages = [
            {
                "role": "system",
                "content": CLARIFY_SYSTEM_PROMPT.format(
                    next_topic=uncovered[0],
                    remaining_count=len(uncovered),
                ),
            },
            *seed,
        ]

        response = await ainvoke_llm(messages)
        ai_text = response.content.strip().strip('"').strip("'")
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
    
    