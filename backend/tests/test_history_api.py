"""GET /sessions: the history page's list of past interviews (Week 5 Step 6)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event

from app.api import sessions as sessions_api
from app.core.security import create_token
from app.models import FeedbackReport, InterviewSession, User


def add_session(
    db, user, template, days_ago=0, status="completed", report=None
) -> InterviewSession:
    session = InterviewSession(
        user=user,
        template=template,
        agent_state={},
        status=status,
        started_at=datetime.now(UTC) - timedelta(days=days_ago),
    )
    db.add(session)
    db.flush()
    if report:
        db.add(FeedbackReport(session_id=session.id, **report))
        db.flush()
    return session


def history(client, headers) -> list[dict]:
    response = client.get("/sessions", headers=headers)
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def other_user(db) -> User:
    other = User(email="other@example.com", password_hash="x", name="Other")
    db.add(other)
    db.flush()
    return other


def test_no_interviews_is_an_empty_list(client, auth_headers):
    assert history(client, auth_headers) == []


def test_row_has_the_date_role_and_score(client, db, user, template, auth_headers):
    session = add_session(db, user, template, report={"status": "ready", "overall_score": 3.25})

    [row] = history(client, auth_headers)

    assert row["id"] == session.id
    assert row["role"] == template.role
    assert row["status"] == "completed"
    assert row["report_status"] == "ready"
    assert row["overall_score"] == 3.25
    assert row["started_at"] is not None


def test_newest_comes_first(client, db, user, template, auth_headers):
    old = add_session(db, user, template, days_ago=5)
    new = add_session(db, user, template, days_ago=1)
    middle = add_session(db, user, template, days_ago=3)

    assert [r["id"] for r in history(client, auth_headers)] == [new.id, middle.id, old.id]


@pytest.mark.parametrize(
    ("session_status", "report", "expected"),
    [
        ("in_progress", None, "not_finished"),
        ("completed", None, "none"),
        ("abandoned", None, "none"),
        ("completed", {"status": "pending"}, "pending"),
        ("completed", {"status": "failed", "error": "secret details"}, "failed"),
    ],
)
def test_interviews_without_a_score_say_why(
    client, db, user, template, auth_headers, session_status, report, expected
):
    add_session(db, user, template, status=session_status, report=report)

    [row] = history(client, auth_headers)

    assert row["report_status"] == expected
    assert row["overall_score"] is None


def test_the_reports_error_is_not_sent(client, db, user, template, auth_headers):
    add_session(db, user, template, report={"status": "failed", "error": "secret details"})

    assert "secret details" not in client.get("/sessions", headers=auth_headers).text


def test_only_my_own_interviews_are_listed(client, db, user, other_user, template, auth_headers):
    mine = add_session(db, user, template)
    add_session(db, other_user, template, report={"status": "ready", "overall_score": 5.0})

    assert [r["id"] for r in history(client, auth_headers)] == [mine.id]


def test_another_users_list_does_not_show_mine(client, db, user, other_user, template):
    add_session(db, user, template)
    headers = {"Authorization": f"Bearer {create_token(other_user.id, 'access')}"}

    assert history(client, headers) == []


def test_needs_login(client):
    assert client.get("/sessions").status_code == 401


def test_list_is_limited_to_the_newest(client, db, user, template, auth_headers, monkeypatch):
    monkeypatch.setattr(sessions_api, "MAX_HISTORY_ROWS", 2)
    add_session(db, user, template, days_ago=3)
    second = add_session(db, user, template, days_ago=2)
    first = add_session(db, user, template, days_ago=1)

    assert [r["id"] for r in history(client, auth_headers)] == [first.id, second.id]


def test_a_long_list_takes_no_more_queries_than_a_short_one(
    client, db, user, template, auth_headers
):
    """One query per row would get slower with every interview (the "N+1" problem)."""

    def count_queries() -> int:
        db.expire_all()  # both counts start with nothing already loaded
        queries = []

        def record(_conn, _cursor, statement, *_args):
            queries.append(statement)

        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", record)
        try:
            history(client, auth_headers)
        finally:
            event.remove(engine, "before_cursor_execute", record)
        return len(queries)

    add_session(db, user, template, report={"status": "ready", "overall_score": 3.0})
    with_one = count_queries()
    for _ in range(5):
        add_session(db, user, template, report={"status": "ready", "overall_score": 3.0})

    assert count_queries() <= with_one
