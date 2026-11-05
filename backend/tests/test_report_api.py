"""GET and POST /sessions/{id}/report: what the report page reads and asks for (Week 5 Step 5)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import create_token
from app.models import FeedbackReport, InterviewSession, User
from app.scoring.rubric import RUBRIC
from app.services.reports import JOB_TIMEOUT_S, REPORT_JOB
from tests.fakes import decision

SCORES = {
    # In the database's own order, as JSONB returns them: not the rubric's.
    name: {
        "score": 3,
        "explanation": f"Why {name}.",
        "examples": [
            {"question": "What is REST?", "quote": "HIDDEN QUOTE", "comment": f"About {name}."}
        ],
    }
    for name in sorted(RUBRIC)
}


@pytest.fixture
def session_id(client, auth_headers, fake_llm, template) -> int:
    fake_llm.script.append(decision("next_question", text="Welcome!"))
    response = client.post("/sessions", json={"template_id": template.id}, headers=auth_headers)
    return response.json()["id"]


@pytest.fixture
def finished(db, session_id) -> int:
    db.get(InterviewSession, session_id).status = "completed"
    db.flush()
    return session_id


def add_report(db, session_id, **fields) -> FeedbackReport:
    report = FeedbackReport(session_id=session_id, **fields)
    db.add(report)
    db.flush()
    return report


def add_ready_report(db, session_id) -> FeedbackReport:
    return add_report(
        db,
        session_id,
        status="ready",
        overall_score=3.25,
        scores=SCORES,
        strengths=["Clear"],
        improvements=["Depth"],
    )


def get_report(client, session_id, headers):
    return client.get(f"/sessions/{session_id}/report", headers=headers)


def ask_for_report(client, session_id, headers):
    return client.post(f"/sessions/{session_id}/report", headers=headers)


def reports_of(db, session_id) -> list[FeedbackReport]:
    db.expire_all()
    return list(db.scalars(select(FeedbackReport).where(FeedbackReport.session_id == session_id)))


@pytest.fixture
def other_headers(db) -> dict[str, str]:
    other = User(email="other@example.com", password_hash="x", name="Other")
    db.add(other)
    db.flush()
    return {"Authorization": f"Bearer {create_token(other.id, 'access')}"}


# --- GET: every state the page can be in -------------------------------------------------------


def test_interview_still_going_has_no_report_to_ask_for(client, auth_headers, session_id):
    body = get_report(client, session_id, auth_headers).json()

    assert body["status"] == "not_finished"
    assert body["can_request"] is False


def test_finished_interview_with_no_report_can_ask_for_one(client, auth_headers, finished):
    """Interviews from before reports existed, or when the queue was down."""
    body = get_report(client, finished, auth_headers).json()

    assert body["status"] == "none"
    assert body["can_request"] is True


def test_new_pending_report_cannot_be_asked_for_again(client, db, auth_headers, finished):
    add_report(db, finished)

    body = get_report(client, finished, auth_headers).json()

    assert body["status"] == "pending"
    assert body["can_request"] is False


def test_pending_report_past_the_jobs_time_limit_can_be_asked_for_again(
    client, db, auth_headers, finished
):
    """A worker killed in the middle of a job leaves a report pending for ever."""
    long_ago = datetime.now(UTC) - timedelta(seconds=JOB_TIMEOUT_S + 60)
    add_report(db, finished, created_at=long_ago)

    assert get_report(client, finished, auth_headers).json()["can_request"] is True


def test_failed_report_can_be_tried_again_and_hides_the_error(client, db, auth_headers, finished):
    add_report(db, finished, status="failed", error="LLMError: secret internal details")

    response = get_report(client, finished, auth_headers)

    assert response.json()["status"] == "failed"
    assert response.json()["can_request"] is True
    assert "secret internal details" not in response.text


def test_ready_report_has_everything_the_page_shows(client, db, auth_headers, finished):
    add_ready_report(db, finished)

    body = get_report(client, finished, auth_headers).json()

    assert body["status"] == "ready"
    assert body["can_request"] is False
    assert body["overall_score"] == 3.25
    assert body["strengths"] == ["Clear"]
    assert body["improvements"] == ["Depth"]
    assert body["criteria"][0] == {
        "name": "technical_accuracy",
        "score": 3,
        "explanation": "Why technical_accuracy.",
        "examples": ["About technical_accuracy."],
    }


def test_criteria_come_in_the_rubrics_order(client, db, auth_headers, finished):
    add_ready_report(db, finished)

    body = get_report(client, finished, auth_headers).json()

    assert [c["name"] for c in body["criteria"]] == list(RUBRIC)


def test_the_hidden_quote_is_never_sent(client, db, auth_headers, finished):
    """It's only there for code to check: the candidate reads the comment."""
    add_ready_report(db, finished)

    assert "HIDDEN QUOTE" not in get_report(client, finished, auth_headers).text


# --- POST: asking for a report -----------------------------------------------------------------


def test_asking_creates_a_report_and_queues_the_job(
    client, db, auth_headers, finished, report_queue
):
    response = ask_for_report(client, finished, auth_headers)

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert response.json()["can_request"] is False
    assert len(reports_of(db, finished)) == 1
    assert report_queue.jobs == [(REPORT_JOB, finished)]


def test_failed_report_starts_again_clean(client, db, auth_headers, finished, report_queue):
    add_report(db, finished, status="failed", error="Gemini was down")

    ask_for_report(client, finished, auth_headers)

    [report] = reports_of(db, finished)
    assert report.status == "pending"
    assert report.error is None
    assert report_queue.jobs == [(REPORT_JOB, finished)]


def test_stuck_report_starts_its_wait_again(client, db, auth_headers, finished, report_queue):
    long_ago = datetime.now(UTC) - timedelta(seconds=JOB_TIMEOUT_S + 60)
    add_report(db, finished, created_at=long_ago)

    response = ask_for_report(client, finished, auth_headers)

    assert response.json()["can_request"] is False
    assert report_queue.jobs == [(REPORT_JOB, finished)]


def test_asking_while_one_is_being_made_does_nothing(
    client, db, auth_headers, finished, report_queue
):
    """A double click shouldn't start a second job."""
    add_report(db, finished)

    response = ask_for_report(client, finished, auth_headers)

    assert response.json()["status"] == "pending"
    assert report_queue.jobs == []


def test_asking_for_a_ready_report_keeps_it(client, db, auth_headers, finished, report_queue):
    add_ready_report(db, finished)

    response = ask_for_report(client, finished, auth_headers)

    assert response.json()["status"] == "ready"
    assert reports_of(db, finished)[0].overall_score == 3.25
    assert report_queue.jobs == []


def test_asking_before_the_interview_ends_is_409(
    client, db, auth_headers, session_id, report_queue
):
    assert ask_for_report(client, session_id, auth_headers).status_code == 409
    assert reports_of(db, session_id) == []
    assert report_queue.jobs == []


# --- Who can see what --------------------------------------------------------------------------


@pytest.mark.parametrize("call", [get_report, ask_for_report])
def test_report_needs_login(client, finished, call):
    assert call(client, finished, {}).status_code == 401


@pytest.mark.parametrize("call", [get_report, ask_for_report])
def test_other_users_report_is_404(client, db, finished, other_headers, report_queue, call):
    add_ready_report(db, finished)

    response = call(client, finished, other_headers)

    assert response.status_code == 404
    assert "Why clarity" not in response.text
    assert report_queue.jobs == []


@pytest.mark.parametrize("call", [get_report, ask_for_report])
def test_missing_session_is_404(client, auth_headers, call):
    assert call(client, 999_999, auth_headers).status_code == 404
