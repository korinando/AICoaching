from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentUser, InterviewerDep
from app.api.schemas import AnswerOut, AnswerRequest, SessionCreate, SessionOut, TurnOut
from app.models import InterviewSession, InterviewTemplate, User
from app.services.interviews import InterviewClosedError, start_interview, submit_answer

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
