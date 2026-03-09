from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse
from src.config.settings import settings
from src.control.voice_assistance.utils import fresh_state, make_gather, say
from src.control.voice_assistance.graph import build_call_graph, build_response_graph
from src.api.rest.dependencies import get_current_user, get_db
from src.core.services.appointment_types import get_appointment_types
from src.control.voice_assistance.session_store import get_session, set_session, delete_session
from src.core.services.user import get_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["Voice Assistance"])

call_graph     = build_call_graph()
response_graph = build_response_graph()

FALLBACK_TEXT  = "I am sorry, something went wrong. Please try again."
NO_SPEECH_TEXT = "Could you please repeat that?"
RETRY_TEXT     = "Sorry, I did not catch that. Please go ahead and speak."
TIMEOUT_TEXT   = "I still could not hear you. Thank you for calling. Goodbye."


def _build_appointment_types(appointment_types: list) -> dict:
    return {at.id: [at.name, at.description] for at in appointment_types}


def _is_call_complete(result: dict) -> bool:
    identity_confirmation_completed = result.get("identity_confirmation_completed", False)
    identity_confirmed_user         = result.get("identity_confirmed_user", False)
    return (
        (identity_confirmation_completed and not identity_confirmed_user)
        or result.get("slot_booked_id") is not None
        or result.get("cancellation_complete", False)
    )


def _build_twiml(ai_text: str, emergency: bool, call_complete: bool) -> str:
    twiml = VoiceResponse()

    if emergency:
        say(twiml, ai_text)
        twiml.dial(settings.EMERGENCY_FORWARD_NUMBER)
        return str(twiml)

    if call_complete:
        say(twiml, ai_text)
        twiml.hangup()
        return str(twiml)

    gather = make_gather()
    say(gather, ai_text)
    twiml.append(gather)

    retry = make_gather()
    say(retry, RETRY_TEXT)
    twiml.append(retry)

    say(twiml, TIMEOUT_TEXT)
    twiml.hangup()

    return str(twiml)


@router.post("/make-call")
async def make_call(
    request: Request,
    to_number: str = Query(...),
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    try:
        result = await call_graph.ainvoke(fresh_state(call_to_number=to_number))
    except Exception as e:
        logger.error("Failed to place call", extra={"to_number": to_number, "error": str(e)})
        return {"status": "error", "detail": "Failed to place call"}

    if result.get("speech_error"):
        logger.error("Call graph speech error", extra={"to_number": to_number, "error": result["speech_error"]})
        return {"status": "error", "detail": result["speech_error"]}

    try:
        user              = await get_user(current_user.get("email"), db)
        appointment_types = await get_appointment_types(db)
    except Exception as e:
        logger.error("Failed to fetch required data for call", extra={"error": str(e)})
        return {"status": "error", "detail": "Failed to fetch required data"}

    call_sid = result.get("call_sid")

    try:
        session_state = fresh_state(
            call_to_number=to_number,
            call_sid=call_sid,
            identity_patient_id=user.id,
            appointment_types=_build_appointment_types(appointment_types),
            identity_user_name=current_user.get("name"),
            identity_user_email=current_user.get("email"),
            identity_user_phone=current_user.get("phone_number"),
        )
        set_session(call_sid, session_state)
    except Exception as e:
        logger.error("Failed to initialize session", extra={"call_sid": call_sid, "error": str(e)})
        return {"status": "error", "detail": "Failed to initialize session"}

    logger.info("Call placed successfully", extra={"call_sid": call_sid, "to_number": to_number})
    return {"status": "call_placed", "call_sid": call_sid}


@router.post("/voice-response")
async def voice_response(request: Request):
    try:
        form     = await request.form()
        call_sid = form.get("CallSid", "unknown")
        speech   = form.get("SpeechResult")
    except Exception as e:
        logger.error("Failed to parse voice response form", extra={"error": str(e)})
        return Response(
            content=_build_twiml(FALLBACK_TEXT, False, True),
            media_type="application/xml",
        )

    try:
        state = get_session(call_sid) or fresh_state(
            call_to_number=form.get("To"),
            call_sid=call_sid
        )
        state["speech_user_text"] = speech.strip() if speech else None
    except Exception as e:
        logger.error("Failed to load session", extra={"call_sid": call_sid, "error": str(e)})
        return Response(
            content=_build_twiml(FALLBACK_TEXT, False, True),
            media_type="application/xml",
        )

    try:
        result = await response_graph.ainvoke(state)
    except Exception as e:
        logger.error("Response graph failed", extra={"call_sid": call_sid, "error": str(e)})
        result = {**state, "speech_ai_text": FALLBACK_TEXT}

    ai_text       = result.get("speech_ai_text") or NO_SPEECH_TEXT
    emergency     = result.get("mapping_emergency", False)
    call_complete = _is_call_complete(result)

    if emergency:
        logger.warning("Emergency call detected", extra={"call_sid": call_sid})

    try:
        if call_complete:
            delete_session(call_sid)
        else:
            set_session(call_sid, result)
    except Exception:
        pass

    return Response(
        content=_build_twiml(ai_text, emergency, call_complete),
        media_type="application/xml",
    )



