"""The live interview WebSocket (Week 4 Step 2). The messages are in ws_messages.py.

A reply is still generated whole and sent as one piece (seq 0), so this works from end to end
before streaming exists. Steps 3-5 replace Interview.think and Interview.speak.

Two things differ from a normal request, because this connection stays open for a whole
interview:
- An async function must never wait on slow work directly: Whisper, Gemini and Piper would
  freeze every other connection on the server. Each stage runs in a thread instead.
- The database connection goes back to the pool after every step (each one ends with a
  commit), so an interview doesn't hold one while the candidate is talking.
"""

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.interviewer import Interviewer
from app.api.deps import DB, AudioStorageDep, InterviewerDep, SpeechToTextDep, TextToSpeechDep
from app.api.ws_messages import (
    AudioChunk,
    Auth,
    EndSession,
    ErrorCode,
    ErrorMessage,
    InterviewerText,
    ServerMessage,
    SessionEnded,
    TextAnswer,
    Transcript,
    TurnComplete,
    parse_client_message,
)
from app.core.security import TokenError, decode_token
from app.models import InterviewSession
from app.services.interviews import (
    InterviewClosedError,
    abandon_interview,
    elapsed_ms,
    speak_turns,
    submit_answer,
)
from app.services.recordings import ProcessedRecording, RecordingError, process_recording
from app.speech.storage import AudioStorage, StorageError
from app.speech.stt import SpeechToText
from app.speech.tts import TextToSpeech

logger = logging.getLogger(__name__)

router = APIRouter(tags=["interview socket"])

# An open connection costs memory, so one that never logs in doesn't get to stay.
AUTH_TIMEOUT_SECONDS = 10
# 4000-4999 is the range WebSockets leave for applications. Like the HTTP codes 401 and 404.
CLOSE_UNAUTHORIZED = 4401
CLOSE_NOT_FOUND = 4404

CLOSED_MESSAGE = "This interview has already finished."
RECORDING_ERROR_CODE: dict[str, ErrorCode] = {
    "too_large": "invalid_audio",
    "empty": "invalid_audio",
    "unreadable": "invalid_audio",
    "too_short": "invalid_audio",
    "no_speech": "no_speech",
    "unavailable": "server_error",
}


class Rejected(Exception):
    """This message can't be handled, but the connection is fine: tell the user and carry on."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Reply:
    turn_index: int
    text: str
    status: str


@dataclass
class Interview:
    """One connection's work. These methods are slow and normal, so they run in a thread."""

    session_id: int
    db: Session
    interviewer: Interviewer
    storage: AudioStorage
    speech_to_text: SpeechToText
    tts: TextToSpeech

    def _session(self) -> InterviewSession:
        # Read again each time: another tab may have changed it since the last step.
        return self.db.get(InterviewSession, self.session_id)

    def belongs_to(self, user_id: int) -> bool:
        """Someone else's session looks the same as a missing one, like the REST endpoints."""
        session = self._session()
        owned = session is not None and session.user_id == user_id
        self.db.commit()
        return owned

    def next_turn(self) -> int:
        """Where the next answer goes. Checked first, so a closed interview does no work."""
        session = self._session()
        if session.status != "in_progress":
            raise Rejected("interview_closed", CLOSED_MESSAGE)
        next_turn = len(session.turns)
        self.db.commit()
        return next_turn

    def transcribe(self, data: bytes) -> ProcessedRecording:
        try:
            return process_recording(data, self.session_id, self.speech_to_text, self.storage)
        except RecordingError as e:
            raise Rejected(RECORDING_ERROR_CODE[e.reason], e.message) from None

    def think(self, text: str, audio_key: str | None, stt_ms: int | None) -> Reply:
        session = self._session()
        try:
            submit_answer(self.db, session, text, self.interviewer, audio_key, stt_ms)
        except InterviewClosedError:
            raise Rejected("interview_closed", CLOSED_MESSAGE) from None
        except IntegrityError:
            # Another tab saved an answer for the same turn first (see submit_answer).
            self.db.rollback()
            raise Rejected(
                "busy", "Another answer was saved first. Reload the interview."
            ) from None
        reply = Reply(session.turns[-1].turn_index, session.turns[-1].text, session.status)
        self.db.commit()
        return reply

    def speak(self, turn_index: int, started: float) -> bytes | None:
        """The reply as a WAV file, or None if the voice failed: the text was already sent."""
        session = self._session()
        turn = session.turns[turn_index]
        speak_turns(self.db, session, [turn], self.tts, self.storage)
        wav = None
        if turn.audio_url is not None:
            try:
                wav = self.storage.load(turn.audio_url)
            except StorageError as e:
                logger.warning("Session %s turn %s: %s", self.session_id, turn_index, e)
        turn.total_latency_ms = elapsed_ms(started)
        self.db.commit()
        return wav

    def abandon(self) -> None:
        try:
            abandon_interview(self.db, self._session())
        except InterviewClosedError:
            raise Rejected("interview_closed", CLOSED_MESSAGE) from None


async def send(websocket: WebSocket, message: ServerMessage) -> None:
    await websocket.send_text(message.model_dump_json())


async def reject(websocket: WebSocket, code: ErrorCode, message: str, close_code: int) -> None:
    """Say why first: a browser's close event can't carry a useful message for the user."""
    await send(websocket, ErrorMessage(code=code, message=message))
    await websocket.close(close_code)


def user_id_from(frame: dict[str, Any]) -> int | None:
    """The user from a first frame, if it's an auth message with a valid access token."""
    try:
        message = parse_client_message(frame.get("text") or "")
        if not isinstance(message, Auth):
            return None
        return decode_token(message.token, expected_type="access")
    except (ValidationError, TokenError):
        return None


async def authenticate(websocket: WebSocket, interview: Interview) -> bool:
    """Everything else waits until this passes. On failure the connection is closed."""
    try:
        async with asyncio.timeout(AUTH_TIMEOUT_SECONDS):
            frame = await websocket.receive()
    except TimeoutError:
        frame = {}
    if frame.get("type") == "websocket.disconnect":
        return False
    user_id = user_id_from(frame)
    if user_id is None:
        await reject(websocket, "unauthorized", "Not authenticated", CLOSE_UNAUTHORIZED)
        return False
    if not await run_in_threadpool(interview.belongs_to, user_id):
        await reject(websocket, "not_found", "Session not found", CLOSE_NOT_FOUND)
        return False
    return True


async def answer(
    websocket: WebSocket,
    interview: Interview,
    text: str | None = None,
    recording: bytes | None = None,
) -> bool:
    """One answer, typed or spoken, through to the whole reply. True if the interview ended."""
    started = time.perf_counter()
    turn_index = await run_in_threadpool(interview.next_turn)
    audio_key, stt_ms = None, None
    if recording is not None:
        processed = await run_in_threadpool(interview.transcribe, recording)
        text, audio_key, stt_ms = processed.text, processed.audio_key, processed.stt_ms
    await send(websocket, Transcript(turn_index=turn_index, text=text))

    reply = await run_in_threadpool(interview.think, text, audio_key, stt_ms)
    await send(websocket, InterviewerText(turn_index=reply.turn_index, seq=0, text=reply.text))

    wav = await run_in_threadpool(interview.speak, reply.turn_index, started)
    if wav is not None:
        # b64encode gives bytes; JSON needs text.
        audio = base64.b64encode(wav).decode("ascii")
        await send(websocket, AudioChunk(turn_index=reply.turn_index, seq=0, audio_base64=audio))
    await send(websocket, TurnComplete(turn_index=reply.turn_index))

    if reply.status == "in_progress":
        return False
    await send(websocket, SessionEnded(status=reply.status))
    return True


async def handle_frame(websocket: WebSocket, interview: Interview, frame: dict[str, Any]) -> bool:
    """One frame after login. True if the interview ended."""
    if frame.get("bytes") is not None:  # a binary frame is always a recording
        return await answer(websocket, interview, recording=frame["bytes"])
    try:
        message = parse_client_message(frame.get("text") or "")
    except ValidationError:
        raise Rejected("invalid_message", "That message wasn't understood.") from None
    match message:
        case TextAnswer():
            return await answer(websocket, interview, text=message.text)
        case EndSession():
            await run_in_threadpool(interview.abandon)
            await send(websocket, SessionEnded(status="abandoned"))
            return True
        case _:  # e.g. a second auth message
            raise Rejected("invalid_message", "That message isn't expected now.")


@router.websocket("/ws/sessions/{session_id}")
async def interview_socket(
    websocket: WebSocket,
    session_id: int,
    db: DB,
    interviewer: InterviewerDep,
    storage: AudioStorageDep,
    speech_to_text: SpeechToTextDep,
    tts: TextToSpeechDep,
) -> None:
    """Answers are handled one at a time, in the order they arrive."""
    interview = Interview(session_id, db, interviewer, storage, speech_to_text, tts)
    await websocket.accept()  # first, or we couldn't receive the token or explain a refusal
    try:
        if not await authenticate(websocket, interview):
            return
        while True:
            frame = await websocket.receive()
            if frame["type"] == "websocket.disconnect":
                return
            try:
                ended = await handle_frame(websocket, interview, frame)
            except Rejected as e:
                await send(websocket, ErrorMessage(code=e.code, message=e.message))
            except WebSocketDisconnect:
                raise
            except Exception:
                # One failed answer shouldn't end the interview: what's committed stays saved.
                logger.exception("Session %s: answer failed", session_id)
                await run_in_threadpool(db.rollback)
                message = "Something went wrong. Please try again."
                await send(websocket, ErrorMessage(code="server_error", message=message))
            else:
                if ended:
                    await websocket.close()
                    return
    except WebSocketDisconnect:
        # The candidate left while a reply was on its way. Anything committed stays saved, and
        # GET /sessions/{id} shows it when they come back.
        logger.info("Session %s: disconnected", session_id)
