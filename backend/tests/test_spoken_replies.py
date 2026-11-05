"""The interviewer's voice: replies get audio, failures fall back to text (Week 3 Step 6)."""

import pytest

from app.agent.interviewer import REPEAT_TEXT
from app.core.security import create_token
from app.models import User
from app.speech.storage import StorageError
from app.speech.tts import TextToSpeechError
from tests.fakes import ANSWER, decision, spoken, streamed
from tests.ws_client import answer_on_socket

OPENING = "Welcome! What is REST?"
REPLY = "Why stateless?"


@pytest.fixture
def session_id(client, auth_headers, fake_llm, template) -> int:
    fake_llm.script.append(decision("next_question", text=OPENING))
    response = client.post("/sessions", json={"template_id": template.id}, headers=auth_headers)
    return response.json()["id"]


def turns(client, session_id, headers) -> list[dict]:
    return client.get(f"/sessions/{session_id}", headers=headers).json()["turns"]


def get_audio(client, session_id, turn_index, headers):
    return client.get(f"/sessions/{session_id}/turns/{turn_index}/audio", headers=headers)


# --- Replies get a voice -----------------------------------------------------------------------


def test_opening_question_is_spoken(client, auth_headers, session_id, tts):
    assert tts.calls == [OPENING]

    response = get_audio(client, session_id, 0, auth_headers)

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == spoken(OPENING)


def test_only_the_reply_is_spoken_not_my_answer(
    client, user, auth_headers, session_id, fake_llm, tts
):
    fake_llm.script.append(streamed("follow_up", REPLY))

    answer_on_socket(client, session_id, user.id, text=ANSWER)

    assert tts.calls == [OPENING, REPLY]
    assert get_audio(client, session_id, 2, auth_headers).content == spoken(REPLY)


def test_fixed_rule_replies_are_spoken_too(client, user, session_id, tts):
    """The Week 1 "say a bit more" reply never calls the LLM, but still needs a voice."""
    answer_on_socket(client, session_id, user.id, text="ok")

    assert tts.calls[-1] == REPEAT_TEXT


def test_transcript_reload_says_which_turns_have_audio(
    client, user, auth_headers, session_id, fake_llm
):
    """After F5 the page must know which replies can be replayed."""
    fake_llm.script.append(streamed("follow_up", REPLY))
    answer_on_socket(client, session_id, user.id, text=ANSWER)

    assert [t["has_audio"] for t in turns(client, session_id, auth_headers)] == [True, False, True]


# --- If the voice fails, the interview carries on with text --------------------------------------


def test_voice_failure_still_gives_the_reply_as_text(
    client, user, auth_headers, session_id, fake_llm, tts
):
    tts.error = TextToSpeechError("voice file missing")
    fake_llm.script.append(streamed("follow_up", REPLY))

    answer_on_socket(client, session_id, user.id, text=ANSWER)

    reply = turns(client, session_id, auth_headers)[-1]
    assert reply["text"] == REPLY
    assert reply["has_audio"] is False


def test_storage_failure_still_gives_the_reply_as_text(
    client, user, auth_headers, session_id, fake_llm, storage
):
    fake_llm.script.append(streamed("follow_up", REPLY))
    storage.error = StorageError("connection refused")

    answer_on_socket(client, session_id, user.id, text=ANSWER)

    storage.error = None
    assert turns(client, session_id, auth_headers)[-1]["has_audio"] is False


def test_interview_can_start_when_the_voice_is_down(client, auth_headers, fake_llm, template, tts):
    tts.error = TextToSpeechError("voice file missing")
    fake_llm.script.append(decision("next_question", text=OPENING))

    response = client.post("/sessions", json={"template_id": template.id}, headers=auth_headers)

    assert response.status_code == 201
    assert response.json()["turns"][0]["has_audio"] is False


# --- GET .../turns/{turn_index}/audio ------------------------------------------------------------


def test_turn_without_audio_is_404(client, user, auth_headers, session_id, fake_llm):
    fake_llm.script.append(streamed("follow_up", REPLY))
    answer_on_socket(client, session_id, user.id, text=ANSWER)  # a typed answer has no recording

    assert get_audio(client, session_id, 1, auth_headers).status_code == 404


def test_missing_turn_is_404(client, auth_headers, session_id):
    assert get_audio(client, session_id, 99, auth_headers).status_code == 404


def test_audio_needs_login(client, session_id):
    assert get_audio(client, session_id, 0, headers={}).status_code == 401


def test_other_users_audio_is_404(client, db, session_id):
    """Someone's voice has the same protection as their transcript (Step 7)."""
    other = User(email="other@example.com", password_hash="x", name="Other")
    db.add(other)
    db.flush()
    headers = {"Authorization": f"Bearer {create_token(other.id, 'access')}"}

    assert get_audio(client, session_id, 0, headers).status_code == 404


def test_storage_down_when_loading_is_503(client, auth_headers, session_id, storage):
    storage.error = StorageError("connection refused")

    assert get_audio(client, session_id, 0, auth_headers).status_code == 503
