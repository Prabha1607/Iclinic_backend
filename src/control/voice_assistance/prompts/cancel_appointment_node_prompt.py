SELECT_SLOT_PROMPT = """
You are a medical voice assistant.

The user has the following appointments on {date}:
{slots_list}

The user said: "{user_text}"

Match what the user said to one of the time slots above (by start time, end time, or appointment type).
Reply ONLY with the exact slot index number (e.g. 1, 2, 3...) from the list above.
If you cannot match, reply: UNKNOWN
"""

CONFIRM_PROMPT = """
You are a medical voice assistant.

The user wants to cancel this appointment:
Type   : {appointment_type}
Date   : {date}
Time   : {start_time} to {end_time}
Reason : {reason}

The user said: "{user_text}"

If the user clearly agrees to cancel, reply: YES
If the user declines or is unsure, reply: NO
Reply ONLY YES or NO.
"""

SELECT_DATE_PROMPT = """
You are a medical voice assistant.

The user has upcoming appointments on these dates:
{dates_list}

The user said: "{user_text}"

Match what the user said to one of the dates above.
Reply ONLY with the date in YYYY-MM-DD format.
If you cannot match, reply: UNKNOWN
"""

ERROR_RESPONSE        = "Something went wrong. Please try again."
DB_ERROR_RESPONSE     = "Something went wrong while fetching your appointments. Please try again."
CANCEL_ERROR_RESPONSE = "Something went wrong while cancelling. Please try again."
NO_APPOINTMENTS_RESPONSE = "You have no upcoming appointments that can be cancelled."