"""Feedback reports: asked for when an interview ends, safe to run twice (Week 5 Steps 2 and 4).

The scorer is a fake here. The scoring itself comes in Step 3.
"""

import asyncio

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.agent.interviewer import Interviewer
from app.api import ws as ws_api
from app.api.deps import get_speech_to_text
from app.core.security import create_token
from app.main import app
from app.models import FeedbackReport, InterviewSession
from app.services.reports import REPORT_JOB, fill_report, request_report
from tests.fakes import ANSWER, FakeSpeechToText, decision, streamed

SCORED = {
    "overall_score": 3.5,
    "scores": {"clarity": 4},
    "strengths": ["Clear"],
    "improvements": ["More depth"],
}


@pytest.fixture(autouse=True)
def speech(client) -> FakeSpeechToText:
    fake = FakeSpeechToText()
    app.dependency_overrides[get_speech_to_text] = lambda: fake
    return fake


@pytest.fixture
def session_id(client, auth_headers, fake_llm, template) -> int:
    fake_llm.script.append(decision("next_question", text="Welcome! What is REST?"))
    response = client.post("/sessions", json={"template_id": template.id}, headers=auth_headers)
    return response.json()["id"]


@pytest.fixture
def finished(db, session_id) -> int:
    db.get(InterviewSession, session_id).status = "completed"
    db.flush()
    return session_id


def on_last_topic(db, session_id) -> None:
    session = db.get(InterviewSession, session_id)
    session.agent_state = {**session.agent_state, "current_topic_index": 4}
    db.flush()


def reports_of(db, session_id) -> list[FeedbackReport]:
    db.expire_all()
    return list(db.scalars(select(FeedbackReport).where(FeedbackReport.session_id == session_id)))


def login(socket, user) -> None:
    socket.send_json({"type": "auth", "token": create_token(user.id, "access")})


# --- Asking for a report when an interview ends ----------------------------------------------


def test_agent_ending_the_interview_asks_for_a_report(
    client, db, user, session_id, fake_llm, report_queue
):
    on_last_topic(db, session_id)
    fake_llm.script.append(streamed("end", "Thank you."))

    with client.websocket_connect(f"/ws/sessions/{session_id}") as socket:
        login(socket, user)
        socket.send_json({"type": "text_answer", "text": ANSWER})
        while socket.receive_json()["type"] != "session_ended":
            pass

    [report] = reports_of(db, session_id)
    assert report.status == "pending"
    assert report_queue.jobs == [(REPORT_JOB, session_id)]


def test_user_ending_the_interview_asks_for_a_report(client, db, user, session_id, report_queue):
    with client.websocket_connect(f"/ws/sessions/{session_id}") as socket:
        login(socket, user)
        socket.send_json({"type": "end_session"})
        assert socket.receive_json()["status"] == "abandoned"

    assert len(reports_of(db, session_id)) == 1
    assert report_queue.jobs == [(REPORT_JOB, session_id)]


def test_interview_still_going_asks_for_nothing(
    client, db, user, session_id, fake_llm, report_queue
):
    fake_llm.script.append(streamed("follow_up"))

    with client.websocket_connect(f"/ws/sessions/{session_id}") as socket:
        login(socket, user)
        socket.send_json({"type": "text_answer", "text": ANSWER})
        while socket.receive_json()["type"] != "turn_complete":
            pass

    assert reports_of(db, session_id) == []
    assert report_queue.jobs == []


def test_report_is_asked_for_even_if_the_candidate_has_left(
    db, session_id, fake_llm, tts, storage, speech, report_queue
):
    class GoneSocket(ws_api.WebSocket):
        def __init__(self) -> None:
            self.application_state = ws_api.WebSocketState.DISCONNECTED

    on_last_topic(db, session_id)
    fake_llm.script.append(streamed("end", "Thank you."))
    interview = ws_api.Interview(
        session_id, db, Interviewer(fake_llm), storage, speech, tts, report_queue
    )

    asyncio.run(ws_api.answer(GoneSocket(), interview, text=ANSWER))

    assert report_queue.jobs == [(REPORT_JOB, session_id)]


def test_voice_crash_on_the_last_reply_still_asks_for_a_report(
    client, db, user, session_id, fake_llm, tts, report_queue
):
    """The interview was saved as finished before the voices were waited for."""
    on_last_topic(db, session_id)
    tts.error = RuntimeError("a bug in the voice")
    fake_llm.script.append(streamed("end", "Thank you."))

    with client.websocket_connect(f"/ws/sessions/{session_id}") as socket:
        login(socket, user)
        socket.send_json({"type": "text_answer", "text": ANSWER})
        while socket.receive_json()["type"] != "error":
            pass

    assert report_queue.jobs == [(REPORT_JOB, session_id)]


def test_redis_down_does_not_stop_the_interview_ending(client, db, user, session_id, report_queue):
    report_queue.error = RedisConnectionError("connection refused")

    with client.websocket_connect(f"/ws/sessions/{session_id}") as socket:
        login(socket, user)
        socket.send_json({"type": "end_session"})
        assert socket.receive_json()["status"] == "abandoned"

    assert db.get(InterviewSession, session_id).status == "abandoned"
    [report] = reports_of(db, session_id)
    assert report.status == "pending"  # waits for scripts/retry_reports.py


def test_asking_twice_is_still_one_report(db, finished, report_queue):
    request_report(db, report_queue, finished)
    request_report(db, report_queue, finished)

    assert len(reports_of(db, finished)) == 1


def test_the_database_refuses_a_second_report(db, finished):
    db.add(FeedbackReport(session_id=finished))
    db.flush()
    db.add(FeedbackReport(session_id=finished))

    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# --- The worker's job ------------------------------------------------------------------------


def test_job_fills_in_the_report(db, finished, report_queue):
    request_report(db, report_queue, finished)

    fill_report(db, finished, lambda session: SCORED)

    [report] = reports_of(db, finished)
    assert report.status == "ready"
    assert report.overall_score == 3.5
    assert report.scores == SCORED["scores"]
    assert report.strengths == SCORED["strengths"]
    assert report.improvements == SCORED["improvements"]
    assert report.error is None


def test_running_the_job_twice_scores_once(db, finished, report_queue):
    request_report(db, report_queue, finished)
    calls = []

    def scorer(session):
        calls.append(session.id)
        return SCORED

    fill_report(db, finished, scorer)
    fill_report(db, finished, scorer)

    assert calls == [finished]
    assert len(reports_of(db, finished)) == 1


def test_failure_is_saved_and_raises_nothing(db, finished, report_queue):
    request_report(db, report_queue, finished)

    def scorer(session):
        raise ValueError("score out of range")

    fill_report(db, finished, scorer)

    [report] = reports_of(db, finished)
    assert report.status == "failed"
    assert report.error == "ValueError: score out of range"
    assert report.overall_score is None


def test_incomplete_result_is_a_failure_not_half_a_report(db, finished, report_queue):
    request_report(db, report_queue, finished)

    fill_report(db, finished, lambda session: {"overall_score": 4.0})

    [report] = reports_of(db, finished)
    assert report.status == "failed"
    assert report.overall_score is None
    assert "KeyError" in report.error


def test_failed_report_can_be_tried_again(db, finished, report_queue):
    request_report(db, report_queue, finished)

    def scorer(session):
        raise ValueError("Gemini is down")

    fill_report(db, finished, scorer)
    fill_report(db, finished, lambda session: SCORED)

    [report] = reports_of(db, finished)
    assert report.status == "ready"
    assert report.error is None


def test_very_long_error_is_cut(db, finished, report_queue):
    request_report(db, report_queue, finished)

    def scorer(session):
        raise ValueError("x" * 10_000)

    fill_report(db, finished, scorer)

    assert len(reports_of(db, finished)[0].error) == 2000


def test_interview_still_going_is_not_scored(db, session_id, report_queue):
    request_report(db, report_queue, session_id)
    calls = []

    fill_report(db, session_id, lambda session: calls.append(session.id))

    assert calls == []
    assert reports_of(db, session_id)[0].status == "pending"


def test_job_with_no_report_does_nothing(db, finished):
    fill_report(db, finished, lambda session: pytest.fail("should not score"))

    assert reports_of(db, finished) == []
