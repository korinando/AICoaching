"""GET /templates and the /sessions endpoints, through HTTP with a fake LLM."""

import pytest

from app.agent.interviewer import CLOSING_TEXT, REPEAT_TEXT
from app.core.security import create_token
from app.models import User
from tests.fakes import ANSWER, decision

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
        }
    ]


def test_create_session_needs_login(client, template):
    assert client.post("/sessions", json={"template_id": template.id}).status_code == 401


def test_create_session_unknown_template_is_404(client, auth_headers, fake_llm):
    response = client.post("/sessions", json={"template_id": 999_999}, headers=auth_headers)

    assert response.status_code == 404
    assert fake_llm.calls == []  # no LLM call for a request that can't succeed


# --- POST /sessions/{id}/answer ----------------------------------------------------------------


def test_answer_returns_only_the_new_turns(client, auth_headers, fake_llm, template):
    session = start(client, auth_headers, fake_llm, template)
    fake_llm.script.append(decision("follow_up", text="Why stateless?"))

    response = client.post(
        f"/sessions/{session['id']}/answer", json={"text": ANSWER}, headers=auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_progress"
    assert [(t["turn_index"], t["speaker"], t["text"]) for t in body["turns"]] == [
        (1, "candidate", ANSWER),
        (2, "interviewer", "Why stateless?"),
    ]


def test_short_answer_gets_repeat_text_without_llm(client, auth_headers, fake_llm, template):
    """The Week 1 rules still apply through the API."""
    session = start(client, auth_headers, fake_llm, template)
    calls_after_start = len(fake_llm.calls)

    response = client.post(
        f"/sessions/{session['id']}/answer", json={"text": "ok"}, headers=auth_headers
    )

    assert response.json()["turns"][-1]["text"] == REPEAT_TEXT
    assert len(fake_llm.calls) == calls_after_start


def test_answer_too_long_is_422(client, auth_headers, fake_llm, template):
    session = start(client, auth_headers, fake_llm, template)

    response = client.post(
        f"/sessions/{session['id']}/answer", json={"text": "x" * 4001}, headers=auth_headers
    )

    assert response.status_code == 422


def test_full_interview_then_answer_is_409(client, auth_headers, fake_llm, template):
    session = start(client, auth_headers, fake_llm, template)
    fake_llm.script.extend([decision("next_question")] * 5)
    url = f"/sessions/{session['id']}/answer"

    for _ in range(5):
        response = client.post(url, json={"text": ANSWER}, headers=auth_headers)

    assert response.json()["status"] == "completed"
    assert response.json()["turns"][-1]["text"] == CLOSING_TEXT
    assert client.post(url, json={"text": ANSWER}, headers=auth_headers).status_code == 409


# --- GET /sessions/{id} ------------------------------------------------------------------------


def test_get_session_returns_full_transcript(client, auth_headers, fake_llm, template):
    """What the chat page loads after a refresh: every turn, in order."""
    session = start(client, auth_headers, fake_llm, template)
    fake_llm.script.append(decision("follow_up", text="Why stateless?"))
    client.post(f"/sessions/{session['id']}/answer", json={"text": ANSWER}, headers=auth_headers)

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


def test_other_user_cannot_answer_session(client, auth_headers, other_headers, fake_llm, template):
    session = start(client, auth_headers, fake_llm, template)
    calls_after_start = len(fake_llm.calls)

    response = client.post(
        f"/sessions/{session['id']}/answer", json={"text": ANSWER}, headers=other_headers
    )

    assert response.status_code == 404
    assert len(fake_llm.calls) == calls_after_start  # refused before the agent ran
    # The owner's transcript is untouched: still only the opening question.
    owner_view = client.get(f"/sessions/{session['id']}", headers=auth_headers).json()
    assert [t["text"] for t in owner_view["turns"]] == [OPENING]


def test_owner_still_has_access(client, auth_headers, other_headers, fake_llm, template):
    """Control test: the 404s above come from the ownership check, not from a broken session."""
    session = start(client, auth_headers, fake_llm, template)

    assert client.get(f"/sessions/{session['id']}", headers=auth_headers).status_code == 200
