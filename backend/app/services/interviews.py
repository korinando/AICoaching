"""Interviews in the web app: the Week 1 agent plus saving everything to the database.

The agent itself doesn't change. For each request this module loads the InterviewState
from the session row, lets the Interviewer take one step, and saves the result. Nothing
is kept in memory between requests, so a server restart loses nothing.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.agent.interviewer import Interviewer
from app.agent.schemas import InterviewState
from app.models import InterviewSession, InterviewTemplate, Turn, User


class InterviewClosedError(Exception):
    """The session is no longer in progress, so it can't take answers."""


def state_from_template(template: InterviewTemplate) -> InterviewState:
    """A fresh InterviewState from a template row (like agent.templates.new_state, but from
    the database instead of templates.json)."""
    return InterviewState(
        role=template.role,
        level=template.level,
        interview_type=template.interview_type,
        planned_topics=list(template.topics),
        max_main_questions=template.max_main_questions,
        max_follow_ups=template.max_follow_ups,
    )


def load_state(session: InterviewSession) -> InterviewState:
    """Rebuild the agent's state from the saved JSON. Validation runs again here, so a
    broken or hand-edited agent_state fails loudly instead of confusing the interviewer."""
    return InterviewState.model_validate(session.agent_state)


def _save(
    session: InterviewSession,
    state: InterviewState,
    first_new: int,
    audio_key: str | None = None,
) -> None:
    """Write the agent's state and its new messages to the session. The only place that
    writes both, so agent_state.history and the turns table can't drift apart.

    audio_key belongs to the first new message: the candidate's answer."""
    for index, message in enumerate(state.history[first_new:], start=first_new):
        session.turns.append(
            Turn(
                turn_index=index,
                speaker=message.role,
                text=message.text,
                audio_url=audio_key if index == first_new else None,
            )
        )
    # A new dict, not an in-place change: SQLAlchemy only notices that a JSONB column changed
    # when the attribute is assigned. Mutating the old dict would silently not be saved.
    session.agent_state = state.model_dump(mode="json")
    if state.finished:
        session.status = "completed"
        session.ended_at = datetime.now(UTC)


def start_interview(
    db: Session, user: User, template: InterviewTemplate, interviewer: Interviewer
) -> InterviewSession:
    """Create a session and ask the opening question."""
    state = state_from_template(template)
    interviewer.start(state)
    session = InterviewSession(user=user, template=template, agent_state={})
    _save(session, state, first_new=0)
    db.add(session)
    db.commit()
    return session


def submit_answer(
    db: Session,
    session: InterviewSession,
    answer: str,
    interviewer: Interviewer,
    audio_key: str | None = None,
) -> str:
    """Handle one candidate answer and return the interviewer's reply.

    audio_key: where the recording is stored, for a spoken answer; None for a typed one.
    """
    if session.status != "in_progress":
        raise InterviewClosedError(f"Session {session.id} is {session.status}")
    state = load_state(session)
    first_new = len(state.history)
    reply = interviewer.handle_answer(state, answer)
    # handle_answer adds 2 messages (answer + reply); saving from first_new catches both.
    # If two requests for one session race, both get the same turn_index and the unique
    # constraint (session_id, turn_index) from Step 3 rejects the second commit.
    _save(session, state, first_new, audio_key)
    db.commit()
    return reply
