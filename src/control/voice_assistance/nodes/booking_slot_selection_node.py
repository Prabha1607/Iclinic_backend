from __future__ import annotations
import json
from datetime import date
from src.control.voice_assistance.models import ainvoke_llm, get_llama1
from src.control.voice_assistance.utils import clear_markdown, update_state
from src.control.voice_assistance.utils import (
    build_date_options_text,
    build_slot_context_text,
    exclude_previously_selected_slot,
    format_date,
    format_time,
    get_available_dates,
    get_nearest_alternate_dates,
    group_slots_by_period,
    looks_like_slot_choice,
    slots_for_date,
)
from src.control.voice_assistance.utils import classify_period
from src.data.clients.postgres_client import AsyncSessionLocal
from src.data.models.postgres.appointment import Appointment
from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.ENUM import SlotStatus
from src.data.repositories.generic_crud import bulk_get_instance
from src.control.voice_assistance.prompts.slot_selection_node_prompt import (
    LLM_ALTERNATE_DATE_SYSTEM,
    LLM_ALTERNATE_SLOT_SYSTEM,
    LLM_CONFIRM_SYSTEM,
    LLM_DATE_SYSTEM,
    LLM_PERIOD_SYSTEM,
    LLM_SLOT_SYSTEM,
    NO_SLOTS_RESPONSE,
    SLOT_CONVERSATION_PROMPT,
)


async def _fetch_all_slots(doctor_id: int) -> list[dict]:
    try:
        from datetime import datetime
        async with AsyncSessionLocal() as db:
            today = date.today()
            now_time = datetime.now().time()

            all_slots = await bulk_get_instance(AvailableSlot, db, provider_id=doctor_id, is_active=True)
            future_available = [
                s for s in all_slots
                if s.status == SlotStatus.AVAILABLE
                and (
                    s.availability_date > today
                    or (s.availability_date == today and s.start_time > now_time)
                )
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
                    "display":      f"{format_time(s.start_time)} → {format_time(s.end_time)}",
                    "full_display": f"{format_time(s.start_time)} → {format_time(s.end_time)} on {format_date(s.availability_date)}",
                }
                for s in future_available
                if s.id not in booked_slot_ids
            ]
    except Exception as e:
        print("[_fetch_all_slots] error:", e)
        return []


async def _llm_extract(system: str, human: str) -> dict:
    try:
        llm = get_llama1()
        response = await llm.ainvoke([("system", system), ("human", human)])
        raw = response.content.strip()
        try:
            return json.loads(clear_markdown(raw))
        except Exception as parse_err:
            print("[_llm_extract] parse error:", parse_err, "| raw:", raw)
            return {}
    except Exception as e:
        print("[_llm_extract] error:", e)
        return {}


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except Exception:
        return None


async def _speak(history: list[dict], doctor_name: str, situation: str, context: str, fallback: str) -> str:
    seed = history if history else [{"role": "user", "content": "start"}]
    messages = [
        {
            "role": "system",
            "content": SLOT_CONVERSATION_PROMPT.format(
                doctor_name=doctor_name,
                situation=situation,
                context=context,
            ),
        },
        *seed,
    ]
    try:
        response = await ainvoke_llm(messages)
        return response.content.strip().strip('"').strip("'")
    except Exception as e:
        print("[_speak] error:", e)
        return fallback


async def _resolve_and_confirm_slot(state: dict, matched_slot: dict) -> dict:
    return update_state(
        state,
        slot_stage="ready_to_book",
        slot_selection_completed=True,
        slot_selected=matched_slot,
        slot_selected_start_time=str(matched_slot["start_time"]),
        slot_selected_end_time=str(matched_slot["end_time"]),
        slot_selected_display=matched_slot["display"],
        user_change_request=None,
    )


async def _handle_initial(state: dict, doctor_name: str) -> dict:
    history: list[dict] = list(state.get("slot_selection_history") or [])
    ai_text = await _speak(
        history, doctor_name,
        situation="opening — ask the patient what date they'd like",
        context=f"Doctor: {doctor_name}",
        fallback=f"Now let's find a good time with {doctor_name}. What date were you thinking?",
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(state, slot_stage="ask_date", slot_selection_completed=False, speech_ai_text=ai_text, slot_selection_history=history)


async def _handle_ask_date(state: dict, user_text: str, doctor_name: str, all_slots: list[dict], available_dates: list[date]) -> dict:
    history: list[dict] = list(state.get("slot_selection_history") or [])
    user_change_request: str | None = state.get("user_change_request")
    previous_date: date | None = state.get("slot_chosen_date")

    if user_change_request and previous_date:
        filtered_slots = [s for s in all_slots if s["date"] != previous_date]
        filtered_dates = get_available_dates(filtered_slots) or available_dates
    else:
        filtered_slots = all_slots
        filtered_dates = available_dates

    parsed = await _llm_extract(system=LLM_DATE_SYSTEM.format(today=date.today().isoformat()), human=user_text)
    chosen_date = _parse_date(parsed.get("date"))

    if chosen_date is None:
        ai_text = await _speak(
            history, doctor_name,
            situation="couldn't understand the date the patient said — ask them to clarify",
            context=f"Change request: {user_change_request or 'none'}, Previous date: {format_date(previous_date) if previous_date else 'none'}",
            fallback="Sorry, I didn't quite catch that. Did you have a particular date in mind? You can say something like 'March 8' or 'next Monday'.",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(state, slot_stage="ask_date", speech_ai_text=ai_text, slot_selection_history=history)

    if user_change_request and previous_date and chosen_date == previous_date:
        alt_dates = [d for d in filtered_dates[:3] if d != previous_date]
        ai_text = await _speak(
            history, doctor_name,
            situation="patient picked the same date they already had — offer alternate dates",
            context=f"Same date: {format_date(chosen_date)}, Alternate dates: {', '.join(format_date(d) for d in alt_dates)}",
            fallback=f"That's the same date you had before. Here are some other available dates with {doctor_name}: {', '.join(format_date(d) for d in alt_dates)}. Which would you prefer?",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(state, slot_stage="ask_alternate_date", speech_ai_text=ai_text, slot_selection_history=history)

    date_slots = slots_for_date(filtered_slots, chosen_date)

    if date_slots:
        ai_text = await _speak(
            history, doctor_name,
            situation="confirm the date the patient chose before proceeding",
            context=f"Chosen date: {format_date(chosen_date)}, Doctor: {doctor_name}",
            fallback=f"Got it — {format_date(chosen_date)}. Just to confirm, you'd like to book with {doctor_name} on that date. Is that correct?",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(state, slot_stage="confirm_date", slot_chosen_date=chosen_date, speech_ai_text=ai_text, slot_selection_history=history)

    alts = get_nearest_alternate_dates(chosen_date, filtered_dates)
    if not alts:
        ai_text = await _speak(
            history, doctor_name,
            situation="doctor has no upcoming availability at all",
            context=f"Doctor: {doctor_name}",
            fallback=f"I'm sorry, {doctor_name} has no upcoming availability right now.",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(state, slot_stage="ask_date", speech_ai_text=ai_text, slot_selection_history=history)

    ai_text = await _speak(
        history, doctor_name,
        situation="requested date has no slots — offer nearest alternate dates",
        context=f"Requested: {format_date(chosen_date)}, Alternates: {', '.join(format_date(d) for d in alts)}",
        fallback=f"Unfortunately {doctor_name} isn't available on {format_date(chosen_date)}. The nearest available dates are {', '.join(format_date(d) for d in alts)}. Would any of those work for you?",
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(state, slot_stage="ask_alternate_date", speech_ai_text=ai_text, slot_selection_history=history)


async def _handle_confirm_date(state: dict, user_text: str, doctor_name: str, all_slots: list[dict], available_dates: list[date]) -> dict:
    history: list[dict] = list(state.get("slot_selection_history") or [])
    chosen_date: date = state.get("slot_chosen_date")
    user_change_request: str | None = state.get("user_change_request")

    parsed = await _llm_extract(system=LLM_CONFIRM_SYSTEM, human=user_text)
    confirmed = parsed.get("confirmed")

    if confirmed is True:
        date_slots = slots_for_date(all_slots, chosen_date)
        return await _proceed_to_period({**state, "user_change_request": None, "slot_selection_history": history}, doctor_name, chosen_date, date_slots)

    parsed2 = await _llm_extract(system=LLM_DATE_SYSTEM.format(today=date.today().isoformat()), human=user_text)
    new_date = _parse_date(parsed2.get("date"))

    if user_change_request and chosen_date:
        filtered_slots = [s for s in all_slots if s["date"] != chosen_date]
        filtered_dates = get_available_dates(filtered_slots) or available_dates
    else:
        filtered_slots = all_slots
        filtered_dates = available_dates

    if new_date and new_date != chosen_date:
        date_slots = slots_for_date(filtered_slots, new_date)
        if date_slots:
            ai_text = await _speak(
                history, doctor_name,
                situation="patient gave a new date — confirm it",
                context=f"New date: {format_date(new_date)}, Doctor: {doctor_name}",
                fallback=f"Got it — {format_date(new_date)}. Confirming with {doctor_name} on that date. Is that correct?",
            )
            history.append({"role": "assistant", "content": ai_text})
            return update_state(state, slot_stage="confirm_date", slot_chosen_date=new_date, speech_ai_text=ai_text, slot_selection_history=history)

        alts = get_nearest_alternate_dates(new_date, filtered_dates)
        ai_text = await _speak(
            history, doctor_name,
            situation="new date patient gave also has no slots — offer alternates",
            context=f"Requested: {format_date(new_date)}, Alternates: {', '.join(format_date(d) for d in alts)}",
            fallback=f"Unfortunately {doctor_name} isn't available on {format_date(new_date)}. The nearest available dates are {', '.join(format_date(d) for d in alts)}. Would any of those work?",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(state, slot_stage="ask_alternate_date", speech_ai_text=ai_text, slot_selection_history=history)

    ai_text = await _speak(
        history, doctor_name,
        situation="patient rejected the date — ask them what date they'd prefer",
        context=f"Rejected date: {format_date(chosen_date)}, Doctor: {doctor_name}",
        fallback=f"No problem! What date would you prefer with {doctor_name}?",
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(state, slot_stage="ask_date", slot_chosen_date=None, slot_chosen_period=None, slot_available_list=None, speech_ai_text=ai_text, slot_selection_history=history)


async def _handle_ask_alternate_date(state: dict, user_text: str, doctor_name: str, all_slots: list[dict], available_dates: list[date]) -> dict:
    history: list[dict] = list(state.get("slot_selection_history") or [])
    user_change_request: str | None = state.get("user_change_request")
    previous_date: date | None = state.get("slot_chosen_date")

    if user_change_request and previous_date:
        filtered_slots = [s for s in all_slots if s["date"] != previous_date]
        filtered_dates = get_available_dates(filtered_slots) or available_dates
    else:
        filtered_slots = all_slots
        filtered_dates = available_dates

    parsed = await _llm_extract(
        system=LLM_ALTERNATE_DATE_SYSTEM.format(today=date.today().isoformat(), date_options=build_date_options_text(filtered_dates)),
        human=user_text,
    )
    chosen_date = _parse_date(parsed.get("date"))
    date_slots = slots_for_date(filtered_slots, chosen_date) if chosen_date else []

    if not date_slots:
        ai_text = await _speak(
            history, doctor_name,
            situation="patient didn't pick a valid alternate date — list all available dates",
            context=f"Available dates: {', '.join(format_date(d) for d in filtered_dates)}",
            fallback=f"No problem. Here are all the dates {doctor_name} is available: {', '.join(format_date(d) for d in filtered_dates)}. Which one would you like?",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(state, slot_stage="ask_alternate_date", speech_ai_text=ai_text, slot_selection_history=history)

    ai_text = await _speak(
        history, doctor_name,
        situation="confirm the alternate date the patient chose",
        context=f"Chosen date: {format_date(chosen_date)}, Doctor: {doctor_name}",
        fallback=f"Got it — {format_date(chosen_date)}. Just to confirm, you'd like to book with {doctor_name} on that date. Is that correct?",
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(state, slot_stage="confirm_date", slot_chosen_date=chosen_date, speech_ai_text=ai_text, slot_selection_history=history)


async def _proceed_to_period(state: dict, doctor_name: str, chosen_date: date, date_slots: list[dict]) -> dict:
    history: list[dict] = list(state.get("slot_selection_history") or [])
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None = state.get("slot_selected_start_time")
    prev_end: str | None = state.get("slot_selected_end_time")

    filtered = exclude_previously_selected_slot(date_slots, user_change_request, prev_start, prev_end)
    periods = group_slots_by_period(filtered or date_slots)
    period_names = list(periods.keys())

    if len(period_names) == 1:
        chosen_period = period_names[0]
        period_slots = periods[chosen_period]
        slot_options = ", ".join(s["display"] for s in period_slots)
        ai_text = await _speak(
            history, doctor_name,
            situation="only one period available — present the time slots in that period",
            context=f"Date: {format_date(chosen_date)}, Period: {chosen_period}, Slots: {slot_options}",
            fallback=f"{doctor_name} only has {chosen_period} availability on {format_date(chosen_date)}. The open slots are: {slot_options}. Which time works best?",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(state, slot_stage="ask_slot", slot_chosen_date=chosen_date, slot_chosen_period=chosen_period, slot_available_list=period_slots, speech_ai_text=ai_text, slot_selection_history=history)

    ai_text = await _speak(
        history, doctor_name,
        situation="multiple periods available — ask patient which part of the day they prefer",
        context=f"Date: {format_date(chosen_date)}, Available periods: {', '.join(period_names)}",
        fallback=f"{doctor_name} is available in the {', '.join(period_names)} on {format_date(chosen_date)}. Which part of the day works better for you?",
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(state, slot_stage="ask_period", slot_chosen_date=chosen_date, speech_ai_text=ai_text, slot_selection_history=history)


async def _handle_ask_period(state: dict, user_text: str, doctor_name: str, all_slots: list[dict]) -> dict:
    history: list[dict] = list(state.get("slot_selection_history") or [])
    chosen_date: date = state.get("slot_chosen_date")
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None = state.get("slot_selected_start_time")
    prev_end: str | None = state.get("slot_selected_end_time")

    date_slots = slots_for_date(all_slots, chosen_date)
    filtered = exclude_previously_selected_slot(date_slots, user_change_request, prev_start, prev_end)
    periods = group_slots_by_period(filtered or date_slots)
    period_names = list(periods.keys())

    parsed = await _llm_extract(system=LLM_PERIOD_SYSTEM.format(available_periods=period_names), human=user_text)
    chosen_period = (parsed.get("period") or "").lower()

    if chosen_period not in periods:
        ai_text = await _speak(
            history, doctor_name,
            situation="requested period not available — let patient know and offer what is available",
            context=f"Requested period: {chosen_period or 'unclear'}, Available periods: {', '.join(period_names)}, Date: {format_date(chosen_date)}",
            fallback=f"Sorry, {doctor_name} isn't available {f'in the {chosen_period} ' if chosen_period else ''}on {format_date(chosen_date)}. Available periods are: {', '.join(period_names)}. Which would you prefer?",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(state, slot_stage="ask_period", speech_ai_text=ai_text, slot_selection_history=history)

    period_slots = periods[chosen_period]
    slot_options = ", ".join(s["display"] for s in period_slots)
    ai_text = await _speak(
        history, doctor_name,
        situation="present the available time slots for the chosen period",
        context=f"Date: {format_date(chosen_date)}, Period: {chosen_period}, Slots: {slot_options}",
        fallback=f"Here are the {chosen_period} slots available on {format_date(chosen_date)} with {doctor_name}: {slot_options}. Which time works best?",
    )
    history.append({"role": "assistant", "content": ai_text})
    return update_state(state, slot_stage="ask_slot", slot_chosen_period=chosen_period, slot_available_list=period_slots, speech_ai_text=ai_text, slot_selection_history=history)


async def _handle_ask_slot(state: dict, user_text: str, doctor_name: str, all_slots: list[dict]) -> dict:
    history: list[dict] = list(state.get("slot_selection_history") or [])
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None = state.get("slot_selected_start_time")
    prev_end: str | None = state.get("slot_selected_end_time")
    chosen_date: date = state.get("slot_chosen_date")
    chosen_period: str | None = state.get("slot_chosen_period")

    date_slots = slots_for_date(all_slots, chosen_date)
    period_slots = ([s for s in date_slots if s["period"] == chosen_period] if chosen_period else date_slots) or state.get("slot_available_list") or []
    filtered = exclude_previously_selected_slot(period_slots, user_change_request, prev_start, prev_end) or period_slots

    if user_change_request and not looks_like_slot_choice(user_text):
        slot_options = ", ".join(s["display"] for s in filtered)
        ai_text = await _speak(
            history, doctor_name,
            situation="patient wants to change slot — present the other available times",
            context=f"Date: {format_date(chosen_date)}, Available slots: {slot_options}",
            fallback=f"Sure! Here are the other available times on {format_date(chosen_date)} with {doctor_name}: {slot_options}. Which one would you like?",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(state, slot_stage="ask_slot", slot_available_list=filtered, user_change_request=user_change_request, speech_ai_text=ai_text, slot_selection_history=history)

    parsed = await _llm_extract(system=LLM_SLOT_SYSTEM.format(slots_context=build_slot_context_text(filtered)), human=user_text)
    slot_id = parsed.get("slot_id")

    if not slot_id:
        other_slots = [s for s in all_slots if s["date"] != chosen_date]
        if not other_slots:
            slot_options = ", ".join(s["display"] for s in filtered)
            ai_text = await _speak(
                history, doctor_name,
                situation="no other slots available at all — present what exists on chosen date",
                context=f"Date: {format_date(chosen_date)}, Available slots: {slot_options}",
                fallback=f"There are no other slots available for {doctor_name} right now. The available times on {format_date(chosen_date)} are: {slot_options}. Would any of these work?",
            )
            history.append({"role": "assistant", "content": ai_text})
            return update_state(state, slot_stage="ask_slot", slot_available_list=filtered, speech_ai_text=ai_text, slot_selection_history=history)

        next_dates = sorted({s["date"] for s in other_slots})[:2]
        alt_slots = exclude_previously_selected_slot([s for s in all_slots if s["date"] in next_dates][:5], user_change_request, prev_start, prev_end)
        alt_options = ", ".join(s["full_display"] for s in alt_slots)
        ai_text = await _speak(
            history, doctor_name,
            situation="patient didn't pick a slot — offer alternative slots on nearby dates",
            context=f"Alternate slots: {alt_options}",
            fallback=f"No problem! Here are some alternative slots for {doctor_name}: {alt_options}. Would any of these work?",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(state, slot_stage="ask_alternate_slot", slot_available_list=alt_slots, speech_ai_text=ai_text, slot_selection_history=history)

    matched = next((s for s in filtered if s["id"] == int(slot_id)), filtered[0])
    return await _resolve_and_confirm_slot({**state, "slot_selection_history": history}, matched)


async def _handle_ask_alternate_slot(state: dict, user_text: str, doctor_name: str) -> dict:
    history: list[dict] = list(state.get("slot_selection_history") or [])
    user_change_request: str | None = state.get("user_change_request")
    prev_start: str | None = state.get("slot_selected_start_time")
    prev_end: str | None = state.get("slot_selected_end_time")

    raw_slots = state.get("slot_available_list") or []
    filtered = exclude_previously_selected_slot(raw_slots, user_change_request, prev_start, prev_end) or raw_slots

    parsed = await _llm_extract(system=LLM_ALTERNATE_SLOT_SYSTEM.format(slots_context=build_slot_context_text(filtered, use_full_display=True)), human=user_text)
    slot_id = parsed.get("slot_id")

    if not slot_id:
        ai_text = await _speak(
            history, doctor_name,
            situation="patient rejected all alternate slots — ask them what date they'd prefer instead",
            context=f"Doctor: {doctor_name}",
            fallback=f"No worries! Let's try again — what date works best for you with {doctor_name}?",
        )
        history.append({"role": "assistant", "content": ai_text})
        return update_state(state, slot_stage="ask_date", slot_chosen_date=None, slot_chosen_period=None, slot_available_list=None, speech_ai_text=ai_text, slot_selection_history=history)

    matched = next((s for s in filtered if s["id"] == int(slot_id)), filtered[0])
    return await _resolve_and_confirm_slot({**state, "slot_selection_history": history}, matched)


_STAGE_HANDLERS = {
    "ask_date":           lambda state, user_text, doctor_name, all_slots, available_dates:
                          _handle_ask_date(state, user_text, doctor_name, all_slots, available_dates),
    "confirm_date":       lambda state, user_text, doctor_name, all_slots, available_dates:
                          _handle_confirm_date(state, user_text, doctor_name, all_slots, available_dates),
    "ask_alternate_date": lambda state, user_text, doctor_name, all_slots, available_dates:
                          _handle_ask_alternate_date(state, user_text, doctor_name, all_slots, available_dates),
    "ask_period":         lambda state, user_text, doctor_name, all_slots, _:
                          _handle_ask_period(state, user_text, doctor_name, all_slots),
    "ask_slot":           lambda state, user_text, doctor_name, all_slots, _:
                          _handle_ask_slot(state, user_text, doctor_name, all_slots),
    "ask_alternate_slot": lambda state, user_text, doctor_name, _, __:
                          _handle_ask_alternate_slot(state, user_text, doctor_name),
}


async def slot_selection_node(state: dict) -> dict:
    print("[slot_selection_node] -----------------------------")

    if state.get("slot_booked_id"):
        return {**state, "slot_selection_completed": True}

    doctor_id: int = state.get("doctor_confirmed_id")
    doctor_name: str = state.get("doctor_confirmed_name", "the doctor")
    user_text: str = (state.get("speech_user_text") or "").strip()
    slot_stage: str | None = state.get("slot_stage")
    history: list[dict] = list(state.get("slot_selection_history") or [])

    if user_text:
        history.append({"role": "user", "content": user_text})
        state = {**state, "slot_selection_history": history}

    try:
        all_slots = await _fetch_all_slots(doctor_id)
    except Exception as e:
        print("[slot_selection_node] _fetch_all_slots failed:", e)
        return update_state(state, slot_selection_completed=False, speech_ai_text="Sorry, I ran into an issue fetching available slots. Please try again.")

    if not all_slots:
        return update_state(state, slot_selection_completed=False, speech_ai_text=NO_SLOTS_RESPONSE.format(doctor_name=doctor_name))

    available_dates = get_available_dates(all_slots)

    if slot_stage is None:
        return await _handle_initial(state, doctor_name)

    handler = _STAGE_HANDLERS.get(slot_stage)
    if handler is None:
        print(f"[slot_selection_node] WARNING: unhandled stage='{slot_stage}'")
        return state

    try:
        return await handler(state, user_text, doctor_name, all_slots, available_dates)
    except Exception as e:
        print(f"[slot_selection_node] stage={slot_stage} error:", e)
        return update_state(state, speech_ai_text="Sorry, something went wrong. Could you please repeat that?")
    

    