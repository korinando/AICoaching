"""The agent running on top of the database (Step 5), with a scripted fake LLM."""

import pytest
from sqlalchemy import select

from app.agent.interviewer import CLOSING_TEXT, REPEAT_TEXT, Interviewer
from app.models import InterviewSession
from app.services.interviews import (
    InterviewClosedError,
    load_state,
    save_answer,
    start_interview,
    state_from_template,
)
from tests.fakes import ANSWER, FakeLLMClient, decision, streamed


def opening() -> list:
    """What start() consumes: one decision whose text is the opening question."""
    return [decision("next_question", text="Welcome! What is REST?")]


def answer(db, session: InterviewSession, text: str, interviewer: Interviewer) -> str:
    """One answer the way the WebSocket handles it: load, stream the reply, then save."""
    state = load_state(session)
    first_new = len(state.history)
    reply = "".join(interviewer.stream_answer(state, text)).strip()
    save_answer(db, session, state, first_new, audio_key=None, stt_ms=None, llm_ms=0)
    return reply


def test_state_from_template_copies_settings(template):
    state = state_from_template(template)
    assert state.planned_topics == template.topics
    assert state.max_main_questions == 5
    assert state.history == []


def test_start_saves_session_state_and_first_turn(db, user, template):
    session = start_interview(db, user, template, Interviewer(FakeLLMClient(opening())))

    assert session.status == "in_progress"
    assert [(t.turn_index, t.speaker, t.text) for t in session.turns] == [
        (0, "interviewer", "Welcome! What is REST?")
    ]
    assert load_state(session).history[0].text == "Welcome! What is REST?"


def test_answer_saves_both_messages_as_turns(db, user, template):
    fake = FakeLLMClient([*opening(), streamed("follow_up", "Why stateless?")])
    interviewer = Interviewer(fake)
    session = start_interview(db, user, template, interviewer)

    reply = answer(db, session, ANSWER, interviewer)

    assert reply == "Why stateless?"
    assert [(t.turn_index, t.speaker) for t in session.turns] == [
        (0, "interviewer"),
        (1, "candidate"),
        (2, "interviewer"),
    ]
    assert load_state(session).follow_ups_on_current == 1


def test_turns_always_match_agent_history(db, user, template):
    """agent_state.history and the turns table hold the same conversation, in order."""
    fake = FakeLLMClient([*opening(), streamed("follow_up"), streamed("next_question")])
    interviewer = Interviewer(fake)
    session = start_interview(db, user, template, interviewer)
    answer(db, session, ANSWER, interviewer)
    answer(db, session, "ok", interviewer)  # short answer: saved too, no LLM call
    answer(db, session, ANSWER, interviewer)

    history = load_state(session).history
    assert [(t.speaker, t.text) for t in session.turns] == [(m.role, m.text) for m in history]
    assert REPEAT_TEXT in [t.text for t in session.turns]


def test_interview_resumes_after_restart(db, user, template):
    """Simulates a server restart: a new Interviewer, and the session read back from the DB."""
    first = Interviewer(FakeLLMClient([*opening(), streamed("next_question")]))
    session = start_interview(db, user, template, first)
    answer(db, session, ANSWER, first)  # now on topic 2 (Databases)
    session_id = session.id

    db.expire_all()  # forget everything loaded in memory: the next read hits the database
    reloaded = db.scalar(select(InterviewSession).where(InterviewSession.id == session_id))
    after_restart = Interviewer(FakeLLMClient([streamed("follow_up", "Which index?")]))
    reply = answer(db, reloaded, ANSWER, after_restart)

    assert reply == "Which index?"
    state = load_state(reloaded)
    assert state.current_topic == "Databases"
    assert state.follow_ups_on_current == 1
    assert len(reloaded.turns) == 5


def test_finished_interview_is_completed_and_closed(db, user, template):
    fake = FakeLLMClient([*opening(), *[streamed("next_question")] * 5])
    interviewer = Interviewer(fake)
    session = start_interview(db, user, template, interviewer)
    for _ in range(5):
        reply = answer(db, session, ANSWER, interviewer)

    assert reply == CLOSING_TEXT
    assert session.status == "completed"
    assert session.ended_at is not None

    # Nothing more can be saved, even if a late reply was generated.
    state = load_state(session)
    with pytest.raises(InterviewClosedError):
        save_answer(db, session, state, len(state.history), None, None, 0)
