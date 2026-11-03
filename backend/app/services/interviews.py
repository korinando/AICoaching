"""Interviews in the web app: the Week 1 agent plus saving everything to the database.

The agent itself doesn't change. For each request this module loads the InterviewState
from the session row, lets the Interviewer take one step, and saves the result. Nothing
is kept in memory between requests, so a server restart loses nothing.
"""

import logging
import time
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.agent.interviewer import Interviewer
from app.agent.schemas import InterviewState
from app.models import InterviewSession, InterviewTemplate, Turn, User
from app.speech.storage import AudioStorage, StorageError, new_audio_key
from app.speech.tts import TextToSpeech, TextToSpeechError

logger = logging.getLogger(__name__)


def elapsed_ms(started: float) -> int:
    """Milliseconds since started = time.perf_counter(), a clock made for measuring durations
    (unlike the wall clock, it can't jump when the system time changes)."""
    return round((time.perf_counter() - started) * 1000)


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


def speak_turns(
    db: Session,
    session: InterviewSession,
    turns: Iterable[Turn],
    tts: TextToSpeech,
    storage: AudioStorage,
) -> None:
    """Give the interviewer's new turns a voice. Runs after the answer is committed.

    Audio is a bonus on top of the text: if the voice or the storage fails, the interview
    carries on with that reply as text only (has_audio is False), and nothing is lost.
    """
    for turn in turns:
        if turn.speaker != "interviewer":
            continue
        try:
            started = time.perf_counter()
            wav = tts.synthesize(turn.text)
            tts_ms = elapsed_ms(started)
            key = new_audio_key(session.id)
            storage.save(key, wav, "audio/wav")
        except (TextToSpeechError, StorageError) as e:
            logger.warning("Session %s turn %s has no audio: %s", session.id, turn.turn_index, e)
        else:
            turn.audio_url = key
            turn.tts_ms = tts_ms
    db.commit()


def start_interview(
    db: Session, user: User, template: InterviewTemplate, interviewer: Interviewer
) -> InterviewSession:
    """Create a session and ask the opening question."""
    state = state_from_template(template)
    started = time.perf_counter()
    interviewer.start(state)
    llm_ms = elapsed_ms(started)
    session = InterviewSession(user=user, template=template, agent_state={})
    _save(session, state, first_new=0)
    session.turns[-1].llm_ms = llm_ms
    db.add(session)
    db.commit()
    return session


def abandon_interview(db: Session, session: InterviewSession) -> None:
    """The user ended the interview early. Everything said so far stays saved."""
    if session.status != "in_progress":
        raise InterviewClosedError(f"Session {session.id} is {session.status}")
    session.status = "abandoned"
    session.ended_at = datetime.now(UTC)
    db.commit()


def submit_answer(
    db: Session,
    session: InterviewSession,
    answer: str,
    interviewer: Interviewer,
    audio_key: str | None = None,
    stt_ms: int | None = None,
) -> str:
    """Handle one candidate answer and return the interviewer's reply.

    audio_key and stt_ms: where the recording is stored and how long Whisper took, for a
    spoken answer; None for a typed one.
    """
    if session.status != "in_progress":
        raise InterviewClosedError(f"Session {session.id} is {session.status}")
    state = load_state(session)
    first_new = len(state.history)
    started = time.perf_counter()
    reply = interviewer.handle_answer(state, answer)
    llm_ms = elapsed_ms(started)  # includes any retry; about 0 if a rule answered without the LLM
    # handle_answer adds 2 messages (answer + reply); saving from first_new catches both.
    # If two requests for one session race, both get the same turn_index and the unique
    # constraint (session_id, turn_index) from Step 3 rejects the second commit.
    _save(session, state, first_new, audio_key)
    reply_turn = session.turns[-1]
    reply_turn.stt_ms = stt_ms
    reply_turn.llm_ms = llm_ms
    db.commit()
    return reply
