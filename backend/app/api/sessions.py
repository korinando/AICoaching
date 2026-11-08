from fastapi import APIRouter, Depends, HTTPException, Response, status
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
    SessionSummaryOut,
)
from app.core.observability import bind_session_from_path
from app.models import FeedbackReport, InterviewSession, InterviewTemplate, Turn, User
from app.scoring.rubric import RUBRIC
from app.services.interviews import speak_turns, start_interview
from app.services.reports import can_request_report, get_report, request_report_again
from app.speech.storage import StorageError

# Every route under /sessions/{session_id} tags its log lines and errors with that id (Step 6).
router = APIRouter(
    prefix="/sessions", tags=["sessions"], dependencies=[Depends(bind_session_from_path)]
)

# Enough for a person to look through, and a limit on the work one request can cause.
MAX_HISTORY_ROWS = 100


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


@router.get("")
def list_sessions(db: DB, user: CurrentUser) -> list[SessionSummaryOut]:
    """My interviews, newest first, for the history page.

    One query with joins, not the session objects and their relationships: loading each session's
    template and report separately would cost one more query per row, and get slower over time.
    Outer join on the report: an interview with no report is still listed.
    """
    rows = db.execute(
        select(
            InterviewSession.id,
            InterviewTemplate.role,
            InterviewSession.status,
            InterviewSession.started_at,
            FeedbackReport.status.label("report_status"),
            FeedbackReport.overall_score,
        )
        .join(InterviewTemplate, InterviewSession.template_id == InterviewTemplate.id)
        .outerjoin(FeedbackReport, FeedbackReport.session_id == InterviewSession.id)
        .where(InterviewSession.user_id == user.id)
        .order_by(InterviewSession.started_at.desc())
        .limit(MAX_HISTORY_ROWS)
    ).all()
    return [
        SessionSummaryOut(
            id=row.id,
            role=row.role,
            status=row.status,
            started_at=row.started_at,
            report_status=(
                "not_finished" if row.status == "in_progress" else row.report_status or "none"
            ),
            overall_score=row.overall_score,
        )
        for row in rows
    ]


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
