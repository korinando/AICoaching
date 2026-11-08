"""The daily interview limit per user (Week 7 Step 7). Every turn calls 3 paid services (speech to
text, Gemini, the voice), so one person can't start unlimited interviews in a day."""

from datetime import date

import pytest
from sqlalchemy import select

from app.models import UsageLimit, User
from app.services import usage
from app.services.usage import DailyLimitReachedError, take_daily_session
from tests.fakes import decision

LIMIT = 3


@pytest.fixture(autouse=True)
def small_limit(monkeypatch):
    monkeypatch.setattr(usage, "daily_session_limit", lambda: LIMIT)


def start(client, headers, fake_llm, template):
    fake_llm.script.append(decision("next_question", text="Welcome! What is REST?"))
    return client.post("/sessions", json={"template_id": template.id}, headers=headers)


def test_the_limit_allows_that_many_interviews_then_refuses(
    client, auth_headers, fake_llm, template
):
    for _ in range(LIMIT):
        assert start(client, auth_headers, fake_llm, template).status_code == 201

    refused = start(client, auth_headers, fake_llm, template)
    assert refused.status_code == 429  # Too Many Requests
    assert "3 interviews" in refused.json()["detail"]
    assert fake_llm.script  # refused before Gemini was asked anything


def test_the_count_is_kept_per_user_and_day(db, user):
    today, tomorrow = date(2026, 11, 8), date(2026, 11, 9)
    other = User(email="other@example.com", password_hash="x", name="Other")
    db.add(other)
    db.flush()

    for _ in range(LIMIT):
        take_daily_session(db, user.id, today)
    with pytest.raises(DailyLimitReachedError):
        take_daily_session(db, user.id, today)

    take_daily_session(db, other.id, today)  # someone else isn't affected
    take_daily_session(db, user.id, tomorrow)  # a new day starts from zero
    rows = db.scalars(select(UsageLimit).where(UsageLimit.user_id == user.id)).all()
    assert sorted((r.date, r.sessions_count) for r in rows) == [(today, LIMIT), (tomorrow, 1)]


def test_a_refused_try_does_not_count(db, user):
    day = date(2026, 11, 8)
    for _ in range(LIMIT):
        take_daily_session(db, user.id, day)
    for _ in range(2):
        with pytest.raises(DailyLimitReachedError):
            take_daily_session(db, user.id, day)
    assert db.get(UsageLimit, (user.id, day)).sessions_count == LIMIT


def test_an_interview_that_fails_to_start_gives_its_place_back(
    client, db, user, auth_headers, fake_llm, template
):
    fake_llm.script.append(RuntimeError("a bug while asking the opening question"))
    with pytest.raises(RuntimeError):  # TestClient raises what the app didn't handle
        client.post("/sessions", json={"template_id": template.id}, headers=auth_headers)

    row = db.scalar(select(UsageLimit).where(UsageLimit.user_id == user.id))
    assert row.sessions_count == 0


def test_an_unknown_template_does_not_count(client, db, user, auth_headers):
    client.post("/sessions", json={"template_id": 999_999}, headers=auth_headers)
    assert db.scalar(select(UsageLimit).where(UsageLimit.user_id == user.id)) is None
