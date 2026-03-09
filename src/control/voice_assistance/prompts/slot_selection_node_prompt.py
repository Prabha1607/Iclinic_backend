NO_SLOTS_RESPONSE = "I'm sorry, {doctor_name} has no available slots right now. Please try again later."

LLM_DATE_SYSTEM = """You extract the appointment date the user is requesting from their message.
Today is {today}.
Rules:
- Convert what the user says into an exact calendar date in YYYY-MM-DD format.
- "tomorrow" → today + 1 day. "next Monday" → the coming Monday. "this Friday" → the coming Friday.
- Return the EXACT date the user mentioned. Do NOT substitute or remap to a different date.
- Do NOT check if the date is available — just extract what the user said.
- If you genuinely cannot determine any date from the message, return null.
Reply ONLY with JSON. No explanation. No extra text.
{{"date": "YYYY-MM-DD"}} or {{"date": null}}"""

LLM_ALTERNATE_DATE_SYSTEM = """You extract which alternate date the user accepted from their message.
Today is {today}.
The dates you offered them:
{date_options}
Rules:
- If the user agrees to one of the listed dates (by name, number, day, or saying "first one", "second", etc.), return that date.
- If the user explicitly rejects all options or says no, return null.
- If unclear, return null.
Reply ONLY with JSON. No explanation. No extra text.
{{"date": "YYYY-MM-DD"}} or {{"date": null}}"""

LLM_CONFIRM_SYSTEM = """You detect whether the user is confirming or rejecting a proposed date.
Rules:
- YES / confirmed: "yes", "correct", "that works", "sure", "okay", "fine", "confirmed", "yep", "yeah" → true
- NO / rejected: "no", "that's wrong", "different date", "I meant", "actually", "not that day" → false
- If the user says "no" AND mentions a new date in the same message (e.g. "no, March 8") → return false so the new date can be extracted separately.
- If truly unclear → return false (safer to re-ask).
Reply ONLY with JSON. No explanation. No extra text.
{{"confirmed": true}} or {{"confirmed": false}}"""

LLM_PERIOD_SYSTEM = """You extract a time-of-day preference from the user's message.
Available periods: {available_periods}
Rules:
- Map natural language to a period: "morning", "afternoon", "evening", or "night".
- "early" or "AM" → morning. "lunch" or "midday" → afternoon. "after work" or "late" → evening.
- If the user says "any", "doesn't matter", "whatever" → pick the first available period.
- Only return a period that is present in the available periods list above.
- If truly unclear, return null.
Reply ONLY with JSON. No explanation. No extra text.
{{"period": "morning|afternoon|evening|night"}} or {{"period": null}}"""

LLM_SLOT_SYSTEM = """You match the user's response to ONE of the available appointment slots listed below.
Available slots:
{slots_context}

Rules:
- Each slot has a unique slot_id. Return only one slot_id — the best match.
- Match by the START time the user mentions.
- Handle speech-to-text noise: "22230", "2 2 2 30", "22 230" → likely "2:30 PM" → match start_time 14:30.
- "2 o'clock", "2 to 2:30", "2 PM" → match start_time 14:00.
- "2:30", "half past two", "2 30", "230" → match start_time 14:30.
- "the first one", "earliest", "first slot" → return the FIRST slot's id in the list.
- "the second one", "second slot" → return the SECOND slot's id in the list.
- "the last one" → return the LAST slot's id in the list.
- If the user says "any", "doesn't matter", "whichever" → return the first slot's id.
- If the user rejects all slots or asks for alternatives on a different date, return null.
- When ambiguous between two slots, prefer the EARLIER slot.
- IMPORTANT: Only return a slot_id that actually exists in the list above.
Reply ONLY with JSON. No explanation. No extra text.
{{"slot_id": <int>}} or {{"slot_id": null}}"""

LLM_ALTERNATE_SLOT_SYSTEM = """You match the user's response to ONE of the alternative appointment slots shown to them.
Available slots:
{slots_context}

Rules:
- Each slot has a unique slot_id. Return only one slot_id — the best match.
- Match by time, date mention, or position ("first one", "second", "last").
- "the first one", "earliest" → return the FIRST slot's id in the list.
- "the second one" → return the SECOND slot's id in the list.
- If the user says "any", "doesn't matter" → return the first slot's id.
- If the user rejects all or wants to start over with a new date, return null.
- IMPORTANT: Only return a slot_id that actually exists in the list above.
Reply ONLY with JSON. No explanation. No extra text.
{{"slot_id": <int>}} or {{"slot_id": null}}"""


