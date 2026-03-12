import asyncio
import json

from src.control.voice_assistance.prompts.clarify_node_prompt import (
    CLARIFY_SYSTEM_PROMPT,
    EMERGENCY_RESPONSE,
    FALLBACK_RESPONSE,
    TOPICS,
)
from src.control.voice_assistance.utils import (
    ainvoke_llm_json,
    build_catalogue_lines,
    build_conversation_string,
    collect_stream,
    fallback_appointment_type,
    llm1_invoke_text,
    update_state,
)

_TRIAGE_AND_COVERAGE_SYSTEM_PROMPT = """
You are a medical intake assistant doing two things at once.

TASK 1 — Emergency check
Decide whether the patient's latest message describes an ACTIVE, life-threatening emergency:
chest pain, heart attack, stroke, cannot breathe, severe bleeding, unconscious, seizure,
severe allergic reaction, suspected poisoning.
Anything else (mild/chronic symptoms, confusion, vague replies, noise) → NOT an emergency.
When in doubt: NOT an emergency.

TASK 2 — Coverage check
Read the FULL conversation and decide which of the four intake topics the PATIENT has
clearly and explicitly answered (not just been asked about).

Topic definitions:
1. main symptom or complaint — PASS if patient names something specific ("headache", "fever", "knee pain");
   FAIL if vague ("not feeling well", "I'm sick")
2. when it started / duration — PASS if any time reference given ("since yesterday", "3 days ago");
   FAIL if no time mentioned
3. patient age in years — PASS if a specific number given ("I'm 34", "born in 1990");
   FAIL if vague ("young", "child", "elderly")
4. existing medical conditions or allergies — PASS if specific condition/allergy named OR explicit denial
   ("no allergies", "I'm healthy", "none"); FAIL if not mentioned at all

Return ONLY valid JSON — no markdown, no explanation:
{
  "emergency": true | false,
  "covered_indices": [<1-based topic numbers the patient has clearly answered>]
}

Examples:
  All topics answered, no emergency → {"emergency": false, "covered_indices": [1, 2, 3, 4]}
  Only symptom answered             → {"emergency": false, "covered_indices": [1]}
  Nothing answered yet              → {"emergency": false, "covered_indices": []}
  Emergency detected                → {"emergency": true,  "covered_indices": [1]}
""".strip()


_MAP_AND_REASON_SYSTEM_PROMPT = """
You are a medical appointment classification assistant.

You will receive a completed intake conversation and a catalogue of appointment types.

Your two tasks:
1. Choose the single most appropriate appointment type from the catalogue.
   Rules:
   - Read the ENTIRE conversation (age, symptoms, duration, severity, conditions).
   - Prefer the most specific type that fits the primary complaint.
   - If the patient is under 18, prefer "pediatric" unless a clearly more specific specialist applies.
   - Only classify as "emergency" if the situation is IMMEDIATELY life-threatening RIGHT NOW
     (unconscious, cannot breathe, active stroke/heart attack). Fever, pain, chronic illness → NOT emergency.
   - If the symptom is common/non-specific (fever, cold, fatigue, general pain) → "general_checkup".
   - If nothing fits clearly → "general_checkup".

2. Write a short clinical reason for the visit (1–2 sentences, plain English).
   Example: "Patient reports persistent lower back pain for 3 days with no prior injury."
   Do NOT include the patient name, appointment type name, or any JSON in the reason.

Return ONLY valid JSON — no markdown, no extra text:
{
  "appointment_type_id": <int>,
  "intent": "<lowercase_appointment_type_name>",
  "reason_for_visit": "<1–2 sentence clinical note>"
}
""".strip()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _triage_and_check_coverage(
    user_text: str,
    history: list[dict],
    topics: list[str],
) -> tuple[bool, list[str]]:
    conversation = build_conversation_string(history)
    topics_numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics))

    prompt = (
        f"Patient's latest message: {user_text}\n\n"
        f"Full conversation so far:\n{conversation}\n\n"
        f"Topics to check:\n{topics_numbered}"
    )

    try:
        raw = await llm1_invoke_text([
            ("system", _TRIAGE_AND_COVERAGE_SYSTEM_PROMPT),
            ("human", prompt),
        ])

        clean = raw.strip()
        if clean.startswith("```"):
            clean = "\n".join(l for l in clean.splitlines() if "```" not in l).strip()

        data = json.loads(clean)
        is_emerg = bool(data.get("emergency", False))
        indices  = data.get("covered_indices", [])
        covered  = [
            topics[int(i) - 1]
            for i in indices
            if str(i).strip().isdigit() and 0 <= int(i) - 1 < len(topics)
        ]
        return is_emerg, covered

    except Exception as exc:
        print("[_triage_and_check_coverage error]:", exc)
        return False, []


async def _map_and_extract(
    conversation_str: str,
    appointment_types: dict,
) -> tuple[int, str, str]:
    catalogue = build_catalogue_lines(appointment_types)
    try:
        data = await ainvoke_llm_json([
            ("system", _MAP_AND_REASON_SYSTEM_PROMPT),
            (
                "human",
                f"Appointment type catalogue:\n{catalogue}\n\n"
                f"Full intake conversation:\n{conversation_str}",
            ),
        ])
        appointment_type_id = int(data.get("appointment_type_id"))
        intent           = str(data.get("intent", "")).strip().lower()
        reason_for_visit = str(data.get("reason_for_visit", "")).strip()
        print(f"[_map_and_extract] intent={intent}, type_id={appointment_type_id}")
        print(f"[_map_and_extract] reason_for_visit={reason_for_visit}")
        return appointment_type_id, intent, reason_for_visit
    except Exception as e:
        print("[_map_and_extract error]:", e)
        fb_id, fb_intent = fallback_appointment_type(appointment_types)
        return fb_id, fb_intent, ""


def _build_greeting(user_name: str | None) -> str:
    name_part = f", {user_name}" if user_name else ""
    return (
        f"Hi{name_part}! Thanks for confirming — "
        f"I just need to ask you a few quick questions before we get you booked in. "
    )


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


async def clarify_node(state: dict) -> dict:
    print("[clarify_node] -----------------------------")
    try:
        history: list[dict]     = list(state.get("clarify_conversation_history") or [])
        user_text: str | None   = state.get("speech_user_text")
        covered: list[str]      = list(state.get("clarify_covered_topics") or [])
        user_name: str | None   = state.get("identity_user_name")
        appointment_types: dict = state.get("appointment_types") or {}

        is_first_turn = len(history) == 0

        
        identity_just_confirmed = state.get("identity_confirmation_completed") and is_first_turn

        is_emerg   = False
        full_content = ""

        if user_text and not identity_just_confirmed:
            user_text = user_text.strip()
            history.append({"role": "user", "content": user_text})

            uncovered_before = [t for t in TOPICS if t not in covered]

            clarify_messages = (
                _build_clarify_messages(history, uncovered_before)
                if uncovered_before else None
            )

            if clarify_messages:
                (is_emerg, newly_covered), full_content = await asyncio.gather(
                    _triage_and_check_coverage(user_text, history, TOPICS),
                    collect_stream(clarify_messages),
                )
            else:
                is_emerg, newly_covered = await _triage_and_check_coverage(user_text, history, TOPICS)
                full_content = ""

            for t in TOPICS:
                if t in newly_covered and t not in covered:
                    covered.append(t)

            print("[covered_topics]:", covered)

            if is_emerg:
                return update_state(
                    state,
                    speech_ai_text=EMERGENCY_RESPONSE,
                    mapping_emergency=True,
                    clarify_completed=True,
                    clarify_conversation_history=history,
                    clarify_covered_topics=covered,
                )

        uncovered = [t for t in TOPICS if t not in covered]
        print("[uncovered_topics]:", uncovered)

        if not uncovered:
            conversation_str    = build_conversation_string(history)
            fb_id, fb_intent    = fallback_appointment_type(appointment_types)
            appointment_type_id = fb_id
            intent              = fb_intent
            reason_for_visit    = ""

            if appointment_types:
                try:
                    appointment_type_id, intent, reason_for_visit = await asyncio.wait_for(
                        _map_and_extract(conversation_str, appointment_types),
                        timeout=5.0,
                    )
                except asyncio.TimeoutError:
                    print("[mapping] timed out — using fallback")
                except Exception as e:
                    print("[mapping error]:", e)

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

        # FIX 3: if full_content was already streamed above, use it;
        # otherwise generate now (covers identity_just_confirmed path too)
        if not full_content:
            messages     = _build_clarify_messages(history, uncovered)
            full_content = await collect_stream(messages)

        ai_text = full_content.strip().strip('"').strip("'")
        print("[ai_response]:", ai_text)

        # FIX 1 (cont): is_first_turn is now always defined, prepend greeting
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
    
