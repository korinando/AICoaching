"""The admin check (ADMIN_EMAILS) and the /admin endpoints behind the debug panel."""

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import get_settings
from app.main import app
from app.models import InterviewSession, Turn


@pytest.fixture
def make_admin(client):
    """Call make_admin("x@y.com") to run the test with that email in ADMIN_EMAILS."""

    def _make(*emails: str) -> None:
        settings = get_settings().model_copy(update={"admin_emails": list(emails)})
        app.dependency_overrides[get_settings] = lambda: settings

    return _make  # the client fixture clears the override after the test


@pytest.fixture
def session_with_timings(db, user, template):
    session = InterviewSession(user_id=user.id, template_id=template.id, agent_state={})
    session.turns = [
        Turn(turn_index=1, speaker="candidate", text="An answer", stt_ms=900),
        Turn(turn_index=0, speaker="interviewer", text="Hi", llm_ms=700, tts_ms=300),
        Turn(
            turn_index=2,
            speaker="interviewer",
            text="Why?",
            llm_ms=650,
            tts_ms=250,
            total_latency_ms=1800,
            first_audio_ms=2100,
        ),
    ]
    db.add(session)
    db.flush()
    return session


def test_settings_compare_admin_emails_without_case():
    settings = get_settings().model_copy(update={"admin_emails": ["Admin@Example.com"]})
    assert settings.is_admin("admin@example.com")
    assert not settings.is_admin("someone@example.com")


def test_nobody_is_admin_by_default():
    assert get_settings().model_copy(update={"admin_emails": []}).is_admin("a@b.com") is False


def test_me_says_whether_the_user_is_admin(client, auth_headers, user, make_admin):
    make_admin("someone-else@example.com")
    assert client.get("/auth/me", headers=auth_headers).json()["is_admin"] is False
    make_admin(user.email)
    assert client.get("/auth/me", headers=auth_headers).json()["is_admin"] is True


@pytest.mark.parametrize("path", ["/admin/debug", "/admin/sessions/1/timings"])
def test_admin_routes_need_a_login(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", ["/admin/debug", "/admin/sessions/1/timings"])
def test_admin_routes_refuse_other_users(client, auth_headers, make_admin, path):
    make_admin("someone-else@example.com")
    response = client.get(path, headers=auth_headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "Admins only"


def test_debug_info_for_admin(client, auth_headers, user, make_admin, report_queue):
    make_admin(user.email)
    report_queue.enqueue("score_session", 1)
    body = client.get("/admin/debug", headers=auth_headers).json()
    assert body["database"] == "ok"
    assert body["redis"] == "ok"
    assert body["queued_reports"] == 1
    assert body["llm_model"] == get_settings().llm_model
    # Only the fields we chose: nothing like a key or a password leaks out.
    assert not any("key" in field or "secret" in field for field in body)


def test_debug_info_reports_redis_down(client, auth_headers, user, make_admin, report_queue):
    make_admin(user.email)
    report_queue.error = RedisConnectionError("down")
    body = client.get("/admin/debug", headers=auth_headers).json()
    assert body["redis"] == "unavailable"
    assert body["queued_reports"] is None


def test_timings_in_turn_order(client, auth_headers, user, make_admin, session_with_timings):
    make_admin(user.email)
    response = client.get(
        f"/admin/sessions/{session_with_timings.id}/timings", headers=auth_headers
    )
    assert response.status_code == 200
    turns = response.json()
    assert [t["turn_index"] for t in turns] == [0, 1, 2]
    assert turns[2] == {
        "turn_index": 2,
        "speaker": "interviewer",
        "stt_ms": None,
        "llm_ms": 650,
        "tts_ms": 250,
        "total_latency_ms": 1800,
        "first_audio_ms": 2100,
    }


def test_timings_for_unknown_session_is_404(client, auth_headers, user, make_admin):
    make_admin(user.email)
    response = client.get("/admin/sessions/999999/timings", headers=auth_headers)
    assert response.status_code == 404
