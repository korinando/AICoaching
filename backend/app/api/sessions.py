import time

from fastapi import APIRouter, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.agent.interviewer import Interviewer
from app.api.deps import (
    DB,
    AudioStorageDep,
    CurrentUser,
    InterviewerDep,
    SpeechToTextDep,
    TextToSpeechDep,
)
from app.api.schemas import (
    MAX_ANSWER_CHARS,
    AnswerOut,
    AnswerRequest,
    FirstAudioReport,
    SessionCreate,
    SessionOut,
    TurnOut,
)
from app.models import InterviewSession, InterviewTemplate, Turn, User
from app.services.interviews import (
    InterviewClosedError,
    elapsed_ms,
    speak_turns,
    start_interview,
    submit_answer,
)
from app.speech.audio import AudioError, normalize_audio, wav_duration_seconds
from app.speech.storage import AudioStorage, StorageError, new_audio_key
from app.speech.stt import SpeechToTextError
from app.speech.tts import TextToSpeech

router = APIRouter(prefix="/sessions", tags=["sessions"])

# Opus (Chrome) is about 4 KB per second of speech, so 10 MB is many minutes of talking:
# far more than any answer, but small enough that one request can't fill the server's memory.
MAX_AUDIO_BYTES = 10 * 1024 * 1024
# The plan: reject recordings shorter than about 1 second. The frontend checks this too,
# but the server can't trust the client, so it measures the decoded audio itself.
MIN_AUDIO_SECONDS = 1.0


def _get_own_session(db: DB, session_id: int, user: User) -> InterviewSession:
    """The session, but only if it belongs to this user.

    Someone else's session gives the same 404 as a missing one, so ids can't be probed to
    learn which sessions exist (more in Step 7).
    """
    session = db.get(InterviewSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return session


@router.post("", status_code=status.HTTP_201_CREATED)
def create_session(
    body: SessionCreate,
    db: DB,
    user: CurrentUser,
    interviewer: InterviewerDep,
    tts: TextToSpeechDep,
    storage: AudioStorageDep,
) -> SessionOut:
    """Start an interview: the response already contains the opening question."""
    template = db.get(InterviewTemplate, body.template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    session = start_interview(db, user, template, interviewer)
    speak_turns(db, session, session.turns, tts, storage)
    return SessionOut.model_validate(session)


@router.get("/{session_id}")
def get_session(session_id: int, db: DB, user: CurrentUser) -> SessionOut:
    """The session and its whole transcript (e.g. to redraw the chat after a page refresh)."""
    return SessionOut.model_validate(_get_own_session(db, session_id, user))


@router.post("/{session_id}/answer")
def answer(
    session_id: int,
    body: AnswerRequest,
    db: DB,
    user: CurrentUser,
    interviewer: InterviewerDep,
    tts: TextToSpeechDep,
    storage: AudioStorageDep,
) -> AnswerOut:
    """Send one answer, get the interviewer's reply.

    Temporary: Week 4 replaces this with a WebSocket for voice streaming.
    """
    started = time.perf_counter()
    session = _get_own_session(db, session_id, user)
    return _answer(db, session, body.text, interviewer, tts, storage, started)


def _answer(
    db: DB,
    session: InterviewSession,
    text: str,
    interviewer: Interviewer,
    tts: TextToSpeech,
    storage: AudioStorage,
    started: float,
    audio_key: str | None = None,
    stt_ms: int | None = None,
) -> AnswerOut:
    """Typed and spoken answers both end here: run the agent, save, speak, return new turns."""
    before = len(session.turns)
    try:
        submit_answer(db, session, text, interviewer, audio_key, stt_ms)
    except InterviewClosedError:
        # 409 Conflict: the request is valid, but the session's state doesn't allow it.
        raise HTTPException(status.HTTP_409_CONFLICT, "Interview already finished") from None
    except IntegrityError:
        # Another answer for this session was saved while this one was being processed
        # (e.g. a double click): both tried the same turn_index, and the unique constraint
        # kept only the first. Undo this one; the client reloads the session.
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Another answer was saved first. Reload the interview."
        ) from None
    new_turns = session.turns[before:]
    # After the commit above: the answer is safe even if speaking the reply goes wrong.
    speak_turns(db, session, new_turns, tts, storage)
    new_turns[-1].total_latency_ms = elapsed_ms(started)
    db.commit()
    return AnswerOut(status=session.status, turns=[TurnOut.model_validate(t) for t in new_turns])


@router.get("/{session_id}/turns/{turn_index}/audio")
def get_turn_audio(
    session_id: int, turn_index: int, db: DB, user: CurrentUser, storage: AudioStorageDep
) -> Response:
    """The recording or spoken reply of one turn, through the API and not a public link, so
    the same login and ownership rules protect someone's voice as their transcript."""
    session = _get_own_session(db, session_id, user)
    turn = db.scalar(
        select(Turn).where(Turn.session_id == session.id, Turn.turn_index == turn_index)
    )
    if turn is None or turn.audio_url is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No audio for this turn")
    try:
        return Response(content=storage.load(turn.audio_url), media_type="audio/wav")
    except StorageError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Could not load the audio. Try again."
        ) from None


@router.post("/{session_id}/turns/{turn_index}/first-audio", status_code=status.HTTP_204_NO_CONTENT)
def report_first_audio(
    session_id: int, turn_index: int, body: FirstAudioReport, db: DB, user: CurrentUser
) -> None:
    """The browser reports: end of my speech -> this reply started playing."""
    session = _get_own_session(db, session_id, user)
    turn = db.scalar(
        select(Turn).where(Turn.session_id == session.id, Turn.turn_index == turn_index)
    )
    if turn is None or turn.speaker != "interviewer":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such reply")
    turn.first_audio_ms = body.first_audio_ms
    db.commit()


@router.post("/{session_id}/audio")
def upload_audio(
    session_id: int,
    audio: UploadFile,
    db: DB,
    user: CurrentUser,
    interviewer: InterviewerDep,
    storage: AudioStorageDep,
    speech_to_text: SpeechToTextDep,
    tts: TextToSpeechDep,
) -> AnswerOut:
    """A spoken answer as a file (multipart/form-data, field name "audio").

    Decode -> transcribe -> store -> the same interviewer as typed answers -> spoken reply.
    """
    started = time.perf_counter()  # the upload has already arrived; the browser measures that
    session = _get_own_session(db, session_id, user)
    if session.status != "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, "Interview already finished")

    # The browser sends e.g. "audio/webm;codecs=opus"; the part before ";" is the format.
    # This header is only the client's claim: ffmpeg (Step 3) checks the real content.
    content_type = audio.content_type or ""
    if not content_type.split(";")[0].startswith("audio/"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Expected an audio file")

    # Read at most one byte more than allowed: enough to know it's too big, without
    # loading a huge upload into memory.
    data = audio.file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Recording is too long")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The recording is empty")

    try:
        wav = normalize_audio(data)
    except AudioError:
        # Claimed to be audio, but ffmpeg can't decode it: corrupt, or not audio at all.
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Could not read the recording as audio"
        ) from None
    duration = wav_duration_seconds(wav)
    if duration < MIN_AUDIO_SECONDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Recording is too short")

    stt_started = time.perf_counter()
    try:
        transcript = speech_to_text.transcribe(wav)
    except SpeechToTextError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Could not process the recording. Try again."
        ) from None
    stt_ms = elapsed_ms(stt_started)
    if not transcript:
        # Silence or noise: ask again without a turn, an LLM call, or using up the agent's
        # short-answer retries. The candidate hasn't answered anything yet.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "No speech detected. Please try again."
        )

    # Saved after every check, so rejected uploads never take up storage. The WAV rather
    # than the original: bigger, but one format that every browser can play back.
    key = new_audio_key(session.id)
    try:
        storage.save(key, wav, "audio/wav")
    except StorageError:
        # 503: the request was fine, a service behind the API is down. Trying again may work.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Could not save the recording. Try again."
        ) from None

    # The same limit as typed answers: 10 MB of audio could transcribe to a very long text.
    text = transcript[:MAX_ANSWER_CHARS]
    return _answer(db, session, text, interviewer, tts, storage, started, key, stt_ms)
