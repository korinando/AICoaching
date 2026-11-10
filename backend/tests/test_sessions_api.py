"""GET /templates and the /sessions endpoints, through HTTP with a fake LLM."""

import pytest

from app.core.security import create_token
from app.models import User
from tests.fakes import ANSWER, decision, streamed
from tests.ws_client import answer_on_socket

OPENING = "Welcome! What is REST?"


def start(client, auth_headers, fake_llm, template) -> dict:
    """Create a session; the fake's first decision is the opening question."""
    fake_llm.script.append(decision("next_question", text=OPENING))
    response = client.post("/sessions", json={"template_id": template.id}, headers=auth_headers)
    assert response.status_code == 201
    return response.json()


# --- GET /templates ----------------------------------------------------------------------------


def test_list_templates(client, template):
    response = client.get("/templates")

    assert response.status_code == 200
    [only] = response.json()
    assert only["slug"] == "junior_backend"
    assert only["topics"][0] == "REST APIs"
    assert only["summary"] == template.summary  # shown in the "New interview" picker


# --- POST /sessions ----------------------------------------------------------------------------


def test_create_session_returns_opening_question(client, auth_headers, fake_llm, template):
    body = start(client, auth_headers, fake_llm, template)

    assert body["status"] == "in_progress"
    assert body["turns"] == [
        {
            "turn_index": 0,
            "speaker": "interviewer",
            "text": OPENING,
            "created_at": body["turns"][0]["created_at"],
            "has_audio": True,
        }
    ]


def test_create_session_needs_login(client, template):
    assert client.post("/sessions", json={"template_id": template.id}).status_code == 401


def test_create_session_unknown_template_is_404(client, auth_headers, fake_llm):
    response = client.post("/sessions", json={"template_id": 999_999}, headers=auth_headers)

    assert response.status_code == 404
    assert fake_llm.calls == []  # no LLM call for a request that can't succeed


# --- GET /sessions/{id} ------------------------------------------------------------------------


def test_get_session_returns_full_transcript(client, user, auth_headers, fake_llm, template):
    """What the chat page loads after a refresh: every turn, in order."""
    session = start(client, auth_headers, fake_llm, template)
    fake_llm.script.append(streamed("follow_up", "Why stateless?"))
    answer_on_socket(client, session["id"], user.id, text=ANSWER)

    response = client.get(f"/sessions/{session['id']}", headers=auth_headers)

    assert response.status_code == 200
    assert [t["text"] for t in response.json()["turns"]] == [OPENING, ANSWER, "Why stateless?"]


def test_get_missing_session_is_404(client, auth_headers):
    assert client.get("/sessions/999999", headers=auth_headers).status_code == 404


# --- Ownership (Step 7): another user's session must look like it doesn't exist ---------------


@pytest.fixture
def other_headers(db) -> dict[str, str]:
    """A second, logged-in user: the "attacker" who tries to reach the first user's session."""
    other = User(email="other@example.com", password_hash="not-a-real-hash", name="Other")
    db.add(other)
    db.flush()
    return {"Authorization": f"Bearer {create_token(other.id, 'access')}"}


def test_other_user_cannot_read_session(client, auth_headers, other_headers, fake_llm, template):
    session = start(client, auth_headers, fake_llm, template)

    response = client.get(f"/sessions/{session['id']}", headers=other_headers)
    missing = client.get("/sessions/999999", headers=other_headers)

    assert response.status_code == 404
    # Exactly the same answer as a session that doesn't exist, so trying ids one by one
    # can't reveal which sessions exist.
    assert response.json() == missing.json()


def test_owner_still_has_access(client, auth_headers, other_headers, fake_llm, template):
    """Control test: the 404s above come from the ownership check, not from a broken session."""
    session = start(client, auth_headers, fake_llm, template)

    assert client.get(f"/sessions/{session['id']}", headers=auth_headers).status_code == 200


def test_every_route_of_one_session_tags_its_logs_with_the_session_id():
    """Week 7 Step 6: a log line written while serving /sessions/{id}/... carries that id."""
    from fastapi.routing import APIRoute

    from app.api.sessions import router
    from app.core.observability import bind_session_from_path

    routes = [r for r in router.routes if isinstance(r, APIRoute) and "{session_id}" in r.path]
    assert routes
    for route in routes:
        assert bind_session_from_path in [d.dependency for d in route.dependencies], route.path
