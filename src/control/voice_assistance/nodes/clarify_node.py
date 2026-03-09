from src.control.voice_assistance.utils import (
    build_conversation_string,
    build_symptoms_text,
    generate_next_response,
    is_emergency,
    update_state,
)
from src.control.voice_assistance.models import ainvoke_llm, get_llama1
from src.control.voice_assistance.prompts.clarify_node_prompt import (
    EMERGENCY_SYSTEM_PROMPT,
    CLARIFY_SYSTEM_PROMPT,
    COVERAGE_CHECK_SYSTEM_PROMPT,
    COVERAGE_CHECK_HUMAN_TEMPLATE,
    EMERGENCY_RESPONSE,
    FALLBACK_RESPONSE,
    TOPICS,
)

async def get_covered_topics(conversation: str, topics: list[str]) -> list[str]:
    topics_numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics))

    prompt = COVERAGE_CHECK_HUMAN_TEMPLATE.format(
        conversation=conversation,
        topics_numbered=topics_numbered,
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
            topics[int(part.strip()) - 1]
            for part in raw.split(",")
            if part.strip().isdigit() and 0 <= int(part.strip()) - 1 < len(topics)
        ]

    except Exception as exc:
        print("get_covered_topics error:", str(exc))
        return []


def _build_greeting(user_name: str | None) -> str:
    name_part = f", {user_name}" if user_name else ""
    return (
        f"Hi{name_part}! Thanks for confirming — I just need to ask you a few quick questions "
        f"before we get you booked in. "
    )


async def _update_covered_topics(
    conversation_history: list, covered: list[str]
) -> list[str]:
    unchecked = [t for t in TOPICS if t not in covered]
    if not unchecked:
        return covered

    conversation = build_conversation_string(conversation_history)
    newly_covered = await get_covered_topics(conversation, unchecked)

    result = list(covered)
    for t in TOPICS:
        if t in newly_covered and t not in result:
            result.append(t)
    return result


async def clarify_node(state: dict) -> dict:
    print("[clarify_node] -----------------------------")
    try:
        conversation_history: list[dict] = list(state.get("clarify_conversation_history") or [])
        user_text: str | None = state.get("speech_user_text")
        covered: list[str] = list(state.get("clarify_covered_topics") or [])
        user_name: str | None = state.get("identity_user_name")

        is_first_turn = len(conversation_history) == 0

        if user_text:
            conversation_history.append({"role": "patient", "text": user_text.strip()})
            print("[user_response]:", user_text)

            if await is_emergency(
                user_text,
                get_llama=get_llama1,
                system_prompt=EMERGENCY_SYSTEM_PROMPT,
            ):
                return update_state(
                    state,
                    speech_ai_text=EMERGENCY_RESPONSE,
                    mapping_emergency=True,
                    clarify_completed=True,
                    clarify_conversation_history=conversation_history,
                    clarify_covered_topics=covered,
                )

            covered = await _update_covered_topics(conversation_history, covered)
            print("[covered_topics]:", covered)

        uncovered = [t for t in TOPICS if t not in covered]
        print("[uncovered_topics]:", uncovered)

        if not uncovered:
            symptoms_text = build_symptoms_text(conversation_history, TOPICS)
            print("[symptoms_text]:", symptoms_text)
            return update_state(
                state,
                clarify_symptoms_text=symptoms_text,
                clarify_conversation_history=conversation_history,
                clarify_covered_topics=covered,
                clarify_completed=True,
                speech_ai_text=None,
            )

        conversation = build_conversation_string(conversation_history)

        next_topic = uncovered[0]
        response = await generate_next_response(
            conversation,
            [next_topic],
            model=ainvoke_llm,
            system_prompt=CLARIFY_SYSTEM_PROMPT,
        )
        print("[ai_response]:", response)

        if is_first_turn:
            response = _build_greeting(user_name) + response

        conversation_history.append({"role": "agent", "text": response})

        return update_state(
            state,
            speech_ai_text=response,
            clarify_conversation_history=conversation_history,
            clarify_covered_topics=covered,
            clarify_completed=False,
        )

    except Exception as exc:
        print("clarify_node error:", str(exc))
        return update_state(
            state,
            speech_ai_text=FALLBACK_RESPONSE,
            clarify_completed=True,
            speech_error=str(exc),
        )
    

    