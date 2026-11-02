from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentUser, InterviewerDep
from app.api.schemas import (
    AnswerOut,
    AnswerRequest,
    AudioReceived,
    SessionCreate,
    SessionOut,
    TurnOut,
)
from app.models import InterviewSession, InterviewTemplate, User
from app.services.interviews import InterviewClosedError, start_interview, submit_answer
from app.speech.audio import AudioError, normalize_audio, wav_duration_seconds

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
    body: SessionCreate, db: DB, user: CurrentUser, interviewer: InterviewerDep
) -> SessionOut:
    """Start an interview: the response already contains the opening question."""
    template = db.get(InterviewTemplate, body.template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    session = start_interview(db, user, template, interviewer)
    return SessionOut.model_validate(session)


@router.get("/{session_id}")
def get_session(session_id: int, db: DB, user: CurrentUser) -> SessionOut:
    """The session and its whole transcript (e.g. to redraw the chat after a page refresh)."""
    return SessionOut.model_validate(_get_own_session(db, session_id, user))


@router.post("/{session_id}/answer")
def answer(
    session_id: int, body: AnswerRequest, db: DB, user: CurrentUser, interviewer: InterviewerDep
) -> AnswerOut:
    """Send one answer, get the interviewer's reply.

    Temporary: Week 4 replaces this with a WebSocket for voice streaming.
    """
    session = _get_own_session(db, session_id, user)
    before = len(session.turns)
    try:
        submit_answer(db, session, body.text, interviewer)
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
    return AnswerOut(status=session.status, turns=[TurnOut.model_validate(t) for t in new_turns])


@router.post("/{session_id}/audio")
def upload_audio(session_id: int, audio: UploadFile, db: DB, user: CurrentUser) -> AudioReceived:
    """Receive one spoken answer as a file (multipart/form-data, field name "audio").

    Week 3 Step 2: only checks and measures the upload. Steps 3-6 add ffmpeg, storage,
    speech-to-text and the interviewer's spoken reply.
    """
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

    return AudioReceived(
        size_bytes=len(data),
        content_type=content_type,
        duration_seconds=round(duration, 2),
        wav_bytes=len(wav),
    )
