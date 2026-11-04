"""The live interview WebSocket (Week 4 Steps 2, 5 and 7). The messages are in ws_messages.py.

A reply goes out sentence by sentence. Each sentence's text is sent as soon as it's complete and
its voice starts at the same moment, while a second task sends the finished voices in order.

Two things differ from a normal request, because this connection stays open for a whole
interview:
- An async function must never wait on slow work directly: Whisper, Gemini and Piper would
  freeze every other connection on the server. Each stage runs in a thread instead.
- The database connection goes back to the pool after every step (each one ends with a
  commit), so an interview doesn't hold one while the candidate is talking.

Once the server has an answer, it finishes the reply and saves it even if the candidate has left
(a refresh, a lost connection), so nothing they said is lost. See send and answers_running.
"""

import asyncio
import base64
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import iterate_in_threadpool, run_in_threadpool
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketState

from app.agent.interviewer import Interviewer
from app.agent.schemas import InterviewState
from app.api.deps import DB, AudioStorageDep, InterviewerDep, SpeechToTextDep, TextToSpeechDep
from app.api.ws_messages import (
    AnswerInProgress,
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
    load_state,
    save_answer,
)
from app.services.recordings import ProcessedRecording, RecordingError, process_recording
from app.speech.audio import join_wavs
from app.speech.sentences import split_sentences
from app.speech.storage import AudioStorage, StorageError, new_audio_key
from app.speech.stt import SpeechToText
from app.speech.tts import TextToSpeech, TextToSpeechError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["interview socket"])

# An open connection costs memory, so one that never logs in doesn't get to stay.
AUTH_TIMEOUT_SECONDS = 10
# 4000-4999 is the range WebSockets leave for applications. Like the HTTP codes 401 and 404.
CLOSE_UNAUTHORIZED = 4401
CLOSE_NOT_FOUND = 4404

CLOSED_MESSAGE = "This interview has already finished."
BUSY_MESSAGE = "Your last answer is still being worked on. Please wait for the reply."
ANSWER_POLL_SECONDS = 0.1

# Sessions with an answer being worked on right now. Kept in this process's memory, so it only
# works with one server process: more than one would need something shared, like Redis.
answers_running: set[int] = set()
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
class ReplyStream:
    """A reply on its way. state only has the answer and reply once sentences has been read."""

    state: InterviewState
    first_new: int
    sentences: Iterator[str]

    @property
    def turn_index(self) -> int:
        return self.first_new + 1  # first_new is the answer, and the reply comes right after it


@dataclass
class SpokenSentence:
    wav: bytes
    tts_ms: int


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

    def last_turn(self) -> int:
        last_turn = len(self._session().turns) - 1
        self.db.commit()
        return last_turn

    def transcribe(self, data: bytes) -> ProcessedRecording:
        try:
            return process_recording(data, self.session_id, self.speech_to_text, self.storage)
        except RecordingError as e:
            raise Rejected(RECORDING_ERROR_CODE[e.reason], e.message) from None

    def begin_reply(self, text: str) -> ReplyStream:
        """Nothing runs yet: split_sentences and stream_answer are generators."""
        state = load_state(self._session())
        self.db.commit()  # the database connection goes back while Gemini is talking
        sentences = split_sentences(self.interviewer.stream_answer(state, text))
        return ReplyStream(state, len(state.history), sentences)

    def voice(self, sentence: str) -> SpokenSentence | None:
        """One sentence as a WAV file, or None if the voice failed: the text was already sent.

        Several of these run at once, so this must not touch self.db: a Session is for one
        thread at a time.
        """
        started = time.perf_counter()
        try:
            wav = self.tts.synthesize(sentence)
        except TextToSpeechError as e:
            logger.warning("Session %s has no audio for a sentence: %s", self.session_id, e)
            return None
        return SpokenSentence(wav, elapsed_ms(started))

    def save_reply(
        self, reply: ReplyStream, audio_key: str | None, stt_ms: int | None, llm_ms: int
    ) -> str:
        """Save the answer and reply, once the whole reply is known. Returns the new status."""
        session = self._session()
        try:
            save_answer(self.db, session, reply.state, reply.first_new, audio_key, stt_ms, llm_ms)
        except InterviewClosedError:
            raise Rejected("interview_closed", CLOSED_MESSAGE) from None
        except IntegrityError:
            # Another tab saved an answer for the same turn first (see save_answer).
            self.db.rollback()
            raise Rejected(
                "busy", "Another answer was saved first. Reload the interview."
            ) from None
        status = session.status
        self.db.commit()
        return status

    def keep_voice(self, turn_index: int, spoken: list[SpokenSentence], started: float) -> None:
        """Store the sentences as one file for the replay button, and save the timings."""
        session = self._session()
        turn = session.turns[turn_index]
        if spoken:
            turn.tts_ms = sum(sentence.tts_ms for sentence in spoken)
            try:
                key = new_audio_key(self.session_id)
                self.storage.save(key, join_wavs([s.wav for s in spoken]), "audio/wav")
            except StorageError as e:
                # The candidate heard it already: only the replay button is lost.
                logger.warning("Session %s turn %s: %s", self.session_id, turn_index, e)
            else:
                turn.audio_url = key
        turn.total_latency_ms = elapsed_ms(started)
        self.db.commit()

    def abandon(self) -> None:
        try:
            abandon_interview(self.db, self._session())
        except InterviewClosedError:
            raise Rejected("interview_closed", CLOSED_MESSAGE) from None


async def send(websocket: WebSocket, message: ServerMessage) -> None:
    """Does nothing once the candidate has left: the work carries on, and they see the result
    when they come back."""
    if websocket.application_state != WebSocketState.CONNECTED:
        return
    try:
        await websocket.send_text(message.model_dump_json())
    except WebSocketDisconnect:
        logger.info("A candidate left while a message was on its way")


async def close(websocket: WebSocket, code: int = 1000) -> None:
    if websocket.application_state == WebSocketState.CONNECTED:
        await websocket.close(code)


async def reject(websocket: WebSocket, code: ErrorCode, message: str, close_code: int) -> None:
    """Say why first: a browser's close event can't carry a useful message for the user."""
    await send(websocket, ErrorMessage(code=code, message=message))
    await close(websocket, close_code)


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


async def wait_for_running_answer(websocket: WebSocket, interview: Interview) -> None:
    """The candidate came back while their answer from before is still being worked on.

    turn_complete tells the page to load the saved turns. A simple loop and not an event: the wait
    is short, and there's nothing to clean up.
    """
    if interview.session_id not in answers_running:
        return
    await send(websocket, AnswerInProgress())
    while interview.session_id in answers_running:
        await asyncio.sleep(ANSWER_POLL_SECONDS)
    last_turn = await run_in_threadpool(interview.last_turn)
    await send(websocket, TurnComplete(turn_index=last_turn))


async def send_audio_in_order(
    websocket: WebSocket, turn_index: int, voices: asyncio.Queue
) -> list[SpokenSentence]:
    """Send each sentence's voice, in the order they were queued, until the None at the end.

    Each item is a task that's already running. Waiting for them one at a time doesn't slow them
    down: if the second finishes first, it's simply ready when its turn comes.
    """
    spoken = []
    seq = 0
    while (voice := await voices.get()) is not None:
        sentence = await voice
        if sentence is not None:
            # b64encode gives bytes; JSON needs text.
            audio = base64.b64encode(sentence.wav).decode("ascii")
            await send(websocket, AudioChunk(turn_index=turn_index, seq=seq, audio_base64=audio))
            spoken.append(sentence)
        seq += 1
    return spoken


async def answer(
    websocket: WebSocket,
    interview: Interview,
    text: str | None = None,
    recording: bytes | None = None,
) -> bool:
    """One answer, typed or spoken, through to the whole reply. True if the interview ended."""
    if interview.session_id in answers_running:
        raise Rejected("busy", BUSY_MESSAGE)
    answers_running.add(interview.session_id)
    try:
        return await _work_on_answer(websocket, interview, text, recording)
    finally:
        answers_running.discard(interview.session_id)


async def _work_on_answer(
    websocket: WebSocket, interview: Interview, text: str | None, recording: bytes | None
) -> bool:
    started = time.perf_counter()
    turn_index = await run_in_threadpool(interview.next_turn)
    audio_key, stt_ms = None, None
    if recording is not None:
        processed = await run_in_threadpool(interview.transcribe, recording)
        text, audio_key, stt_ms = processed.text, processed.audio_key, processed.stt_ms
    await send(websocket, Transcript(turn_index=turn_index, text=text))

    reply = await run_in_threadpool(interview.begin_reply, text)
    voices: asyncio.Queue = asyncio.Queue()
    # A task of its own: the loop below spends most of its time waiting for Gemini, and a finished
    # voice shouldn't have to wait for the next sentence.
    sender = asyncio.create_task(send_audio_in_order(websocket, reply.turn_index, voices))
    try:
        thinking = time.perf_counter()
        seq = 0
        # The generators wait on the network, so each next() runs in a thread.
        async for sentence in iterate_in_threadpool(reply.sentences):
            message = InterviewerText(turn_index=reply.turn_index, seq=seq, text=sentence)
            await send(websocket, message)
            voices.put_nowait(asyncio.create_task(run_in_threadpool(interview.voice, sentence)))
            seq += 1
        llm_ms = elapsed_ms(thinking)
        voices.put_nowait(None)
        # Saved before waiting for the voices: if one crashes, the answer isn't lost.
        status = await run_in_threadpool(interview.save_reply, reply, audio_key, stt_ms, llm_ms)
        spoken = await sender
    finally:
        sender.cancel()  # does nothing if it finished; otherwise it must not outlive the reply

    await run_in_threadpool(interview.keep_voice, reply.turn_index, spoken, started)
    await send(websocket, TurnComplete(turn_index=reply.turn_index))

    if status == "in_progress":
        return False
    await send(websocket, SessionEnded(status=status))
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
    if not await authenticate(websocket, interview):
        return
    await wait_for_running_answer(websocket, interview)
    while True:
        frame = await websocket.receive()
        if frame["type"] == "websocket.disconnect":
            return
        try:
            ended = await handle_frame(websocket, interview, frame)
        except Rejected as e:
            await send(websocket, ErrorMessage(code=e.code, message=e.message))
        except Exception:
            # One failed answer shouldn't end the interview: what's committed stays saved.
            logger.exception("Session %s: answer failed", session_id)
            await run_in_threadpool(db.rollback)
            message = "Something went wrong. Please try again."
            await send(websocket, ErrorMessage(code="server_error", message=message))
        else:
            if ended:
                await close(websocket)
                return
