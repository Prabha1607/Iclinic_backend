import json
from datetime import time, date
from src.control.voice_assistance.prompts.slot_selection_node_prompt import (
    LLM_DATE_SYSTEM,
    LLM_ALTERNATE_DATE_SYSTEM,
    LLM_CONFIRM_SYSTEM,
    LLM_PERIOD_SYSTEM,
    LLM_SLOT_SYSTEM,
    LLM_ALTERNATE_SLOT_SYSTEM,
    NO_SLOTS_RESPONSE,
)
from src.data.clients.postgres_client import AsyncSessionLocal
from src.data.repositories.generic_crud import bulk_get_instance
from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.appointment import Appointment
from src.data.models.postgres.ENUM import SlotStatus
from src.control.voice_assistance.models import get_llama1
from src.control.voice_assistance.utils import clear_markdown, update_state

MORNING_START   = time(6, 0)
MORNING_END     = time(12, 0)
AFTERNOON_START = time(12, 0)
AFTERNOON_END   = time(17, 0)
EVENING_START   = time(17, 0)
EVENING_END     = time(21, 0)


def classify_period(t: time) -> str:
    if MORNING_START <= t < MORNING_END:
        return "morning"
    elif AFTERNOON_START <= t < AFTERNOON_END:
        return "afternoon"
    elif EVENING_START <= t < EVENING_END:
        return "evening"
    return "night"


def fmt_time(t: time) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def fmt_date(d: date) -> str:
    return d.strftime("%A, %b %d %Y")


async def fetch_all_slots(doctor_id: int) -> list[dict]:
    try:
        async with AsyncSessionLocal() as db:
            today = date.today()

            all_slots = await bulk_get_instance(AvailableSlot, db, provider_id=doctor_id, is_active=True)

            future_available = [
                s for s in all_slots
                if s.availability_date >= today and s.status == SlotStatus.AVAILABLE
            ]

            all_appointments = await bulk_get_instance(Appointment, db, provider_id=doctor_id, is_active=True)

            booked_slot_ids = {
                a.availability_slot_id for a in all_appointments
                if str(a.status.value).upper() in ("SCHEDULED", "CONFIRMED")
            }

            return [
                {
                    "id":           s.id,
                    "date":         s.availability_date,
                    "start_time":   s.start_time,
                    "end_time":     s.end_time,
                    "period":       classify_period(s.start_time),
                    "display":      f"{fmt_time(s.start_time)} → {fmt_time(s.end_time)}",
                    "full_display": f"{fmt_time(s.start_time)} → {fmt_time(s.end_time)} on {fmt_date(s.availability_date)}",
                }
                for s in future_available
                if s.id not in booked_slot_ids
            ]
    except Exception as e:
        print("[fetch_all_slots error]:", e)
        return []


def slots_for_date(all_slots: list[dict], target: date) -> list[dict]:
    return [s for s in all_slots if s["date"] == target]


def periods_on_date(slots: list[dict]) -> dict[str, list]:
    periods: dict[str, list] = {}
    for s in slots:
        periods.setdefault(s["period"], []).append(s)
    return periods


def _filter_previously_selected_slot(
    slots: list[dict],
    user_change_request: str | None,
    prev_start: str | None,
    prev_end: str | None,
) -> list[dict]:
    if not user_change_request or not prev_start or not prev_end:
        return slots

    def _to_time(val) -> time | None:
        if isinstance(val, time):
            return val
        try:
            return time.fromisoformat(str(val))
        except Exception:
            return None

    prev_start_t = _to_time(prev_start)
    prev_end_t   = _to_time(prev_end)

    if prev_start_t is None or prev_end_t is None:
        return slots

    filtered = [
        s for s in slots
        if not (_to_time(s["start_time"]) == prev_start_t and _to_time(s["end_time"]) == prev_end_t)
    ]

    return filtered if filtered else slots


async def llm_extract(system: str, human: str) -> dict:
    try:
        llm = get_llama1()
        response = await llm.ainvoke([("system", system), ("human", human)])
        raw = response.content.strip()
        try:
            return json.loads(clear_markdown(raw))
        except Exception as e:
            print("[llm_extract parse error]:", e, "| raw:", raw)
            return {}
    except Exception as e:
        print("[llm_extract error]:", e)
        return {}


def _parse_date(chosen_date_str: str | None) -> date | None:
    try:
        return date.fromisoformat(chosen_date_str) if chosen_date_str else None
    except Exception:
        return None


def _build_date_options(available_dates: list[date]) -> str:
    return "\n".join(f"{fmt_date(d)} -> {d.isoformat()}" for d in available_dates)


def _build_slot_context(slots: list[dict], use_full_display: bool = False) -> str:
    display_key = "full_display" if use_full_display else "display"
    return "\n".join(
        f"slot_id={s['id']} start_time={s['start_time']} end_time={s['end_time']} display={s[display_key]}"
        for s in slots
    )


def _nearest_alt_dates(chosen_date: date, available_dates: list[date]) -> list[date]:
    before = sorted([d for d in available_dates if d < chosen_date], reverse=True)
    after  = sorted([d for d in available_dates if d > chosen_date])

    alts = []
    if before:
        alts.append(before[0])
    alts.extend(after[:2])

    if len(alts) < 3:
        if not before and len(after) >= 3:
            alts = after[:3]
        elif not after and len(before) >= 3:
            alts = sorted(before[:3])

    return sorted(set(alts))[:3]


async def _proceed_to_period(state: dict, doctor_name: str, chosen_date: date, date_slots: list) -> dict:
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None          = state.get("slot_selected_start_time")
    prev_end: str | None            = state.get("slot_selected_end_time")

    filtered_date_slots = _filter_previously_selected_slot(date_slots, user_change_request, prev_start, prev_end)

    periods           = periods_on_date(filtered_date_slots)
    available_periods = list(periods.keys())

    if not available_periods:
        periods           = periods_on_date(date_slots)
        available_periods = list(periods.keys())

    if len(available_periods) == 1:
        chosen_period = available_periods[0]
        period_slots  = periods[chosen_period]
        slot_lines    = "\n".join(f"  - {s['display']}" for s in period_slots)
        return update_state(
            state,
            slot_stage="ask_slot",
            slot_chosen_date=chosen_date,
            slot_chosen_period=chosen_period,
            slot_available_list=period_slots,
            speech_ai_text=(
                f"{doctor_name} only has {chosen_period} availability on {fmt_date(chosen_date)}. "
                f"Here are the open slots:\n{slot_lines}\n"
                "Which time works best for you?"
            ),
        )

    period_lines = "\n".join(f"  - {p}" for p in available_periods)
    return update_state(
        state,
        slot_stage="ask_period",
        slot_chosen_date=chosen_date,
        speech_ai_text=(
            f"{doctor_name} is available in the {', '.join(available_periods)} "
            f"on {fmt_date(chosen_date)}.\n{period_lines}\n"
            "Which part of the day works better for you?"
        ),
    )


async def _handle_ask_date(
    state: dict, user_text: str, doctor_name: str, all_slots: list[dict], available_dates: list[date]
) -> dict:
    user_change_request: str | None = state.get("user_change_request")
    previous_date: date | None      = state.get("slot_chosen_date")

    if user_change_request and previous_date:
        filtered_slots  = [s for s in all_slots if s["date"] != previous_date]
        filtered_dates  = sorted({s["date"] for s in filtered_slots})
        if not filtered_slots:
            filtered_slots = all_slots
            filtered_dates = available_dates
    else:
        filtered_slots = all_slots
        filtered_dates = available_dates

    today  = date.today()
    parsed = await llm_extract(
        system=LLM_DATE_SYSTEM.format(today=today.isoformat()),
        human=user_text,
    )

    chosen_date = _parse_date(parsed.get("date"))

    if chosen_date is None:
        change_context = (
            f"The patient previously had {fmt_date(previous_date)} booked and wants to change it. "
            if user_change_request and previous_date else ""
        )
        return update_state(
            state,
            slot_stage="ask_date",
            speech_ai_text=(
                f"{change_context}"
                "Sorry, I didn't quite catch that. "
                "Did you have a particular date in mind? "
                "You can say something like 'March 8' or 'next Monday'."
            ),
        )

    if user_change_request and previous_date and chosen_date == previous_date:
        alt_dates  = [d for d in filtered_dates if d != previous_date]
        alt_lines  = "\n".join(f"  - {fmt_date(d)}" for d in alt_dates[:3])
        return update_state(
            state,
            slot_stage="ask_alternate_date",
            speech_ai_text=(
                f"That's the same date you had before. "
                f"Since you'd like to change, here are other available dates with {doctor_name}:\n"
                f"{alt_lines}\n"
                "Which one would you prefer?"
            ),
        )

    date_slots = slots_for_date(filtered_slots, chosen_date)

    if date_slots:
        return update_state(
            state,
            slot_stage="confirm_date",
            slot_chosen_date=chosen_date,
            speech_ai_text=(
                f"Got it — {fmt_date(chosen_date)}. "
                f"Just to confirm, you'd like to book with {doctor_name} on that date. Is that correct?"
            ),
        )

    alts = _nearest_alt_dates(chosen_date, filtered_dates)

    if not alts:
        return update_state(
            state,
            slot_stage="ask_date",
            speech_ai_text=f"I'm sorry, {doctor_name} has no upcoming availability right now.",
        )

    alt_lines = "\n".join(f"  - {fmt_date(d)}" for d in alts)
    return update_state(
        state,
        slot_stage="ask_alternate_date",
        speech_ai_text=(
            f"Unfortunately {doctor_name} isn't available on {fmt_date(chosen_date)}. "
            f"The nearest available dates are:\n{alt_lines}\n"
            "Would any of those work for you?"
        ),
    )


async def _handle_confirm_date(
    state: dict, user_text: str, doctor_name: str, all_slots: list[dict], available_dates: list[date]
) -> dict:
    chosen_date: date               = state.get("slot_chosen_date")
    user_change_request: str | None = state.get("user_change_request")
    previous_date: date | None      = chosen_date

    parsed    = await llm_extract(system=LLM_CONFIRM_SYSTEM, human=user_text)
    confirmed = parsed.get("confirmed")

    if confirmed is True:
        date_slots = slots_for_date(all_slots, chosen_date)
        new_state  = {**state, "user_change_request": None}
        return await _proceed_to_period(new_state, doctor_name, chosen_date, date_slots)

    today   = date.today()
    parsed2 = await llm_extract(
        system=LLM_DATE_SYSTEM.format(today=today.isoformat()),
        human=user_text,
    )
    new_date = _parse_date(parsed2.get("date"))

    if user_change_request and previous_date:
        filtered_slots = [s for s in all_slots if s["date"] != previous_date]
        filtered_dates = sorted({s["date"] for s in filtered_slots}) or available_dates
    else:
        filtered_slots = all_slots
        filtered_dates = available_dates

    if new_date and new_date != chosen_date:
        date_slots = slots_for_date(filtered_slots, new_date)

        if date_slots:
            return update_state(
                state,
                slot_stage="confirm_date",
                slot_chosen_date=new_date,
                speech_ai_text=(
                    f"Got it — {fmt_date(new_date)}. "
                    f"Confirming with {doctor_name} on that date. Is that correct?"
                ),
            )

        alts      = _nearest_alt_dates(new_date, filtered_dates)
        alt_lines = "\n".join(f"  - {fmt_date(d)}" for d in alts)
        return update_state(
            state,
            slot_stage="ask_alternate_date",
            speech_ai_text=(
                f"Unfortunately {doctor_name} isn't available on {fmt_date(new_date)}. "
                f"The nearest available dates are:\n{alt_lines}\n"
                "Would any of those work for you?"
            ),
        )

    return update_state(
        state,
        slot_stage="ask_date",
        slot_chosen_date=None,
        slot_chosen_period=None,
        slot_available_list=None,
        speech_ai_text=f"No problem! What date would you prefer with {doctor_name}?",
    )


async def _handle_ask_alternate_date(
    state: dict, user_text: str, doctor_name: str, all_slots: list[dict], available_dates: list[date]
) -> dict:
    user_change_request: str | None = state.get("user_change_request")
    previous_date: date | None      = state.get("slot_chosen_date")

    if user_change_request and previous_date:
        filtered_slots  = [s for s in all_slots if s["date"] != previous_date]
        filtered_dates  = sorted({s["date"] for s in filtered_slots}) or available_dates
    else:
        filtered_slots = all_slots
        filtered_dates = available_dates

    today  = date.today()
    parsed = await llm_extract(
        system=LLM_ALTERNATE_DATE_SYSTEM.format(
            today=today.isoformat(),
            date_options=_build_date_options(filtered_dates),
        ),
        human=user_text,
    )

    chosen_date = _parse_date(parsed.get("date"))
    date_slots  = slots_for_date(filtered_slots, chosen_date) if chosen_date else []

    if not date_slots:
        date_lines = "\n".join(f"  - {fmt_date(d)}" for d in filtered_dates)
        return update_state(
            state,
            slot_stage="ask_alternate_date",
            speech_ai_text=(
                f"No problem. Here are all the dates {doctor_name} is available:\n"
                f"{date_lines}\n"
                "Which one would you like?"
            ),
        )

    return update_state(
        state,
        slot_stage="confirm_date",
        slot_chosen_date=chosen_date,
        speech_ai_text=(
            f"Got it — {fmt_date(chosen_date)}. "
            f"Just to confirm, you'd like to book with {doctor_name} on that date. Is that correct?"
        ),
    )


async def _handle_ask_period(
    state: dict, user_text: str, doctor_name: str, all_slots: list[dict]
) -> dict:
    chosen_date: date               = state.get("slot_chosen_date")
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None          = state.get("slot_selected_start_time")
    prev_end: str | None            = state.get("slot_selected_end_time")

    date_slots        = slots_for_date(all_slots, chosen_date)
    filtered_slots    = _filter_previously_selected_slot(date_slots, user_change_request, prev_start, prev_end)
    periods           = periods_on_date(filtered_slots)
    available_periods = list(periods.keys())

    if not available_periods:
        periods           = periods_on_date(date_slots)
        available_periods = list(periods.keys())

    parsed        = await llm_extract(
        system=LLM_PERIOD_SYSTEM.format(available_periods=available_periods),
        human=user_text,
    )
    chosen_period = (parsed.get("period") or "").lower()

    if chosen_period not in periods:
        period_lines = "\n".join(f"  - {p}" for p in available_periods)
        return update_state(
            state,
            slot_stage="ask_period",
            speech_ai_text=(
                f"Sorry, {doctor_name} isn't available "
                f"{'in the ' + chosen_period + ' ' if chosen_period else ''}"
                f"on {fmt_date(chosen_date)}. "
                f"Available periods are:\n{period_lines}\n"
                "Which would you prefer?"
            ),
        )

    period_slots = periods[chosen_period]
    slot_lines   = "\n".join(f"  - {s['display']}" for s in period_slots)

    print(f"------------------[handle_ask_period] chosen_period={chosen_period} slots={period_slots}--------------------------------------")
    return update_state(
        state,
        slot_stage="ask_slot",
        slot_chosen_period=chosen_period,
        slot_available_list=period_slots,
        speech_ai_text=(
            f"Here are the {chosen_period} slots available on {fmt_date(chosen_date)} "
            f"with {doctor_name}:\n{slot_lines}\n"
            "Which time works best for you?"
        ),
    )


async def _handle_ask_slot(
    state: dict, user_text: str, doctor_name: str, all_slots: list[dict]
) -> dict:
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None          = state.get("slot_selected_start_time")
    prev_end: str | None            = state.get("slot_selected_end_time")
    chosen_date: date               = state.get("slot_chosen_date")
    chosen_period: str | None       = state.get("slot_chosen_period")

    # ── Build the slot pool for this date+period, excluding the old slot ──────
    # If slot_available_list is stale (from a previous selection), rebuild it
    # fresh from all_slots so we never miss any slots on the chosen date.
    date_slots    = slots_for_date(all_slots, chosen_date)
    period_slots  = (
        [s for s in date_slots if s["period"] == chosen_period]
        if chosen_period
        else date_slots
    )
    # Fall back to the stored list if fresh fetch yields nothing
    if not period_slots:
        period_slots = state.get("slot_available_list") or []

    filtered_slots = _filter_previously_selected_slot(period_slots, user_change_request, prev_start, prev_end)
    if not filtered_slots:
        filtered_slots = period_slots

    # ── If this is a fresh change_slot entry (no real slot choice yet), ───────
    # just present the remaining slots without trying to parse a slot_id.
    if user_change_request and not _looks_like_slot_choice(user_text):
        slot_lines = "\n".join(f"  - {s['display']}" for s in filtered_slots)
        return update_state(
            state,
            slot_stage="ask_slot",
            slot_available_list=filtered_slots,
            user_change_request=user_change_request,  # keep flag alive for filter
            speech_ai_text=(
                f"Sure! Here are the other available times on {fmt_date(chosen_date)} "
                f"with {doctor_name}:\n{slot_lines}\n"
                "Which one would you like?"
            ),
        )

    # ── Normal slot parsing ───────────────────────────────────────────────────
    parsed  = await llm_extract(
        system=LLM_SLOT_SYSTEM.format(slots_context=_build_slot_context(filtered_slots)),
        human=user_text,
    )
    slot_id = parsed.get("slot_id")

    if not slot_id:
        # No match on the chosen date — offer other dates
        other_slots = [s for s in all_slots if s["date"] != chosen_date]

        if not other_slots:
            slot_lines = "\n".join(f"  - {s['display']}" for s in filtered_slots)
            return update_state(
                state,
                slot_stage="ask_slot",
                slot_available_list=filtered_slots,
                speech_ai_text=(
                    f"There are no other slots available for {doctor_name} right now. "
                    f"The available times on {fmt_date(chosen_date)} are:\n{slot_lines}\n"
                    "Would any of these work?"
                ),
            )

        next_dates     = sorted({s["date"] for s in other_slots})[:2]
        alt_date_slots = [s for s in all_slots if s["date"] in next_dates][:5]
        alt_date_slots = _filter_previously_selected_slot(alt_date_slots, user_change_request, prev_start, prev_end)
        alt_lines      = "\n".join(f"  - {s['full_display']}" for s in alt_date_slots)
        return update_state(
            state,
            slot_stage="ask_alternate_slot",
            slot_available_list=alt_date_slots,
            speech_ai_text=(
                f"No problem! Here are some alternative slots for {doctor_name}:\n"
                f"{alt_lines}\n"
                "Would any of these work for you?"
            ),
        )

    matched = next((s for s in filtered_slots if s["id"] == int(slot_id)), filtered_slots[0])
    return update_state(
        state,
        slot_stage="ready_to_book",
        slot_selection_completed=True,
        slot_selected=matched,
        slot_selected_start_time=str(matched["start_time"]),
        slot_selected_end_time=str(matched["end_time"]),
        slot_selected_display=matched["display"],
        user_change_request=None,   # clear the flag once a new slot is chosen
    )


def _looks_like_slot_choice(text: str) -> bool:
    """
    Returns True if the user text looks like an actual time/slot selection
    (e.g. '9:30', '10 AM', '9 to 9:30') rather than a change-intent phrase
    (e.g. 'I want to change the time').
    This prevents the LLM from being called with a non-slot sentence and
    accidentally falling through to the alternate-dates branch.
    """
    import re
    time_pattern = re.compile(
        r'\b(\d{1,2}(:\d{2})?\s*(am|pm|AM|PM)?'   # e.g. 9, 9:30, 9 AM
        r'|morning|afternoon|evening|night'          # period words
        r'|first|second|last|other|another)\b',      # ordinal / vague picks
        re.IGNORECASE,
    )
    return bool(time_pattern.search(text))


async def _handle_ask_alternate_slot(
    state: dict, user_text: str, doctor_name: str, all_slots: list[dict], available_dates: list[date]
) -> dict:
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None          = state.get("slot_selected_start_time")
    prev_end: str | None            = state.get("slot_selected_end_time")

    raw_period_slots: list = state.get("slot_available_list", [])
    period_slots           = _filter_previously_selected_slot(raw_period_slots, user_change_request, prev_start, prev_end)

    if not period_slots:
        period_slots = raw_period_slots

    parsed  = await llm_extract(
        system=LLM_ALTERNATE_SLOT_SYSTEM.format(
            slots_context=_build_slot_context(period_slots, use_full_display=True)
        ),
        human=user_text,
    )
    slot_id = parsed.get("slot_id")

    if not slot_id:
        return update_state(
            state,
            slot_stage="ask_date",
            slot_chosen_date=None,
            slot_chosen_period=None,
            slot_available_list=None,
            speech_ai_text=f"No worries! Let's try again — what date works best for you with {doctor_name}?",
        )

    matched = next((s for s in period_slots if s["id"] == int(slot_id)), period_slots[0])
    return update_state(
        state,
        slot_stage="ready_to_book",
        slot_selection_completed=True,
        slot_selected=matched,
        slot_selected_start_time=str(matched["start_time"]),
        slot_selected_end_time=str(matched["end_time"]),
        slot_selected_display=matched["display"],
        user_change_request=None,
    )


async def slot_selection_node(state: dict) -> dict:
    print("[slot_selection_node] -----------------------------")

    if state.get("slot_booked_id"):
        return {**state, "slot_selection_completed": True}

    doctor_id:           int      = state.get("doctor_confirmed_id")
    doctor_name:         str      = state.get("doctor_confirmed_name", "the doctor")
    user_text:           str      = (state.get("speech_user_text") or "").strip()
    slot_stage:          str      = state.get("slot_stage")
    user_change_request: str|None = state.get("user_change_request")

    try:
        all_slots = await fetch_all_slots(doctor_id)
    except Exception as e:
        print("[slot_selection_node] fetch_all_slots failed:", e)
        return update_state(
            state,
            slot_selection_completed=False,
            speech_ai_text="Sorry, I ran into an issue fetching available slots. Please try again.",
        )

    if not all_slots:
        return update_state(
            state,
            slot_selection_completed=False,
            speech_ai_text=NO_SLOTS_RESPONSE.format(doctor_name=doctor_name),
        )

    available_dates = sorted({s["date"] for s in all_slots})

    if slot_stage is None:
        return update_state(
            state,
            slot_stage="ask_date",
            slot_selection_completed=False,
            speech_ai_text=(
                f"Great! Now let's find a good time with {doctor_name}. "
                f"What date were you thinking?"
            ),
        )

    handler_map = {
        "ask_date":           lambda: _handle_ask_date(state, user_text, doctor_name, all_slots, available_dates),
        "confirm_date":       lambda: _handle_confirm_date(state, user_text, doctor_name, all_slots, available_dates),
        "ask_alternate_date": lambda: _handle_ask_alternate_date(state, user_text, doctor_name, all_slots, available_dates),
        "ask_period":         lambda: _handle_ask_period(state, user_text, doctor_name, all_slots),
        "ask_slot":           lambda: _handle_ask_slot(state, user_text, doctor_name, all_slots),
        "ask_alternate_slot": lambda: _handle_ask_alternate_slot(state, user_text, doctor_name, all_slots, available_dates),
    }

    handler = handler_map.get(slot_stage)
    if handler is None:
        return state

    try:
        return await handler()
    except Exception as e:
        print(f"[slot_selection_node] stage={slot_stage} error:", e)
        return update_state(
            state,
            speech_ai_text="Sorry, something went wrong. Could you please repeat that?",
        )