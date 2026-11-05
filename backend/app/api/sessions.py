from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import (
    DB,
    AudioStorageDep,
    CurrentUser,
    InterviewerDep,
    ReportQueueDep,
    TextToSpeechDep,
)
from app.api.schemas import (
    FirstAudioReport,
    ReportCriterionOut,
    ReportOut,
    SessionCreate,
    SessionOut,
)
from app.models import FeedbackReport, InterviewSession, InterviewTemplate, Turn, User
from app.scoring.rubric import RUBRIC
from app.services.interviews import speak_turns, start_interview
from app.services.reports import can_request_report, get_report, request_report_again
from app.speech.storage import StorageError

router = APIRouter(prefix="/sessions", tags=["sessions"])


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


def _report_out(session: InterviewSession, report: FeedbackReport | None) -> ReportOut:
    if session.status == "in_progress":
        return ReportOut(status="not_finished", can_request=False)
    if report is None:
        return ReportOut(status="none", can_request=True)
    if report.status != "ready":
        return ReportOut(status=report.status, can_request=can_request_report(report))
    return ReportOut(
        status="ready",
        can_request=False,
        overall_score=report.overall_score,
        # The rubric's order: JSONB returns keys in its own.
        criteria=[
            ReportCriterionOut(
                name=name,
                score=report.scores[name]["score"],
                explanation=report.scores[name]["explanation"],
                examples=[example["comment"] for example in report.scores[name]["examples"]],
            )
            for name in RUBRIC
        ],
        strengths=report.strengths,
        improvements=report.improvements,
    )


@router.get("/{session_id}/report")
def read_report(session_id: int, db: DB, user: CurrentUser) -> ReportOut:
    """The report page asks this every few seconds until the report has left "pending"."""
    session = _get_own_session(db, session_id, user)
    return _report_out(session, get_report(db, session.id))


@router.post("/{session_id}/report", status_code=status.HTTP_202_ACCEPTED)
def ask_for_report(session_id: int, db: DB, user: CurrentUser, queue: ReportQueueDep) -> ReportOut:
    """Create a report, or try again after a failure. 202: accepted, but the work comes later."""
    session = _get_own_session(db, session_id, user)
    if session.status == "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, "The interview hasn't ended yet")
    request_report_again(db, queue, session.id)
    return _report_out(session, get_report(db, session.id))
