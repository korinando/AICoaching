"""Latency numbers saved on each reply (Week 3 Step 7). Tests that they're saved in the right
place, not how fast anything is: speed depends on the machine."""

import pytest
from sqlalchemy import select

from app.agent.interviewer import REPEAT_TEXT
from app.api.deps import get_speech_to_text
from app.core.security import create_token
from app.main import app
from app.models import Turn, User
from app.speech.tts import TextToSpeechError
from scripts.latency_report import RULE_REPLIES, percentile, summary_line
from tests.fakes import ANSWER, FakeSpeechToText, decision, streamed
from tests.ws_client import answer_on_socket


@pytest.fixture
def session_id(client, auth_headers, fake_llm, template) -> int:
    app.dependency_overrides[get_speech_to_text] = lambda: FakeSpeechToText()
    fake_llm.script.append(decision("next_question", text="Welcome!"))
    response = client.post("/sessions", json={"template_id": template.id}, headers=auth_headers)
    return response.json()["id"]


def turn(db, session_id, turn_index) -> Turn:
    db.expire_all()
    return db.scalar(
        select(Turn).where(Turn.session_id == session_id, Turn.turn_index == turn_index)
    )


def report(client, session_id, turn_index, headers, ms=1234):
    return client.post(
        f"/sessions/{session_id}/turns/{turn_index}/first-audio",
        json={"first_audio_ms": ms},
        headers=headers,
    )


def test_spoken_reply_has_every_stage(client, db, user, session_id, fake_llm, audio_samples):
    fake_llm.script.append(streamed("follow_up"))

    answer_on_socket(client, session_id, user.id, recording=audio_samples["webm"])

    reply = turn(db, session_id, 2)
    assert reply.stt_ms is not None
    assert reply.llm_ms is not None
    assert reply.tts_ms is not None
    assert reply.total_latency_ms is not None
    # Whisper and Gemini run one after the other. Piper isn't added: its sentences run at the same
    # time as each other and as Gemini, so its sum can be longer than the real wait.
    assert reply.total_latency_ms >= reply.stt_ms + reply.llm_ms


def test_timings_are_on_the_reply_not_on_my_answer(
    client, db, user, session_id, fake_llm, audio_samples
):
    fake_llm.script.append(streamed("follow_up"))

    answer_on_socket(client, session_id, user.id, recording=audio_samples["webm"])

    answer = turn(db, session_id, 1)
    assert answer.stt_ms is None and answer.llm_ms is None and answer.total_latency_ms is None


def test_typed_answer_has_no_speech_to_text_time(client, db, user, session_id, fake_llm):
    fake_llm.script.append(streamed("follow_up"))

    answer_on_socket(client, session_id, user.id, text=ANSWER)

    reply = turn(db, session_id, 2)
    assert reply.stt_ms is None
    assert reply.llm_ms is not None


def test_voice_failure_leaves_tts_empty_but_keeps_the_total(
    client, db, user, session_id, fake_llm, tts, audio_samples
):
    tts.error = TextToSpeechError("voice file missing")
    fake_llm.script.append(streamed("follow_up"))

    answer_on_socket(client, session_id, user.id, recording=audio_samples["webm"])

    reply = turn(db, session_id, 2)
    assert reply.tts_ms is None
    assert reply.total_latency_ms is not None


# --- POST .../first-audio --------------------------------------------------------------------


def test_browser_report_is_saved_on_the_reply(client, db, auth_headers, session_id):
    response = report(client, session_id, 0, auth_headers, ms=2500)

    assert response.status_code == 204
    assert turn(db, session_id, 0).first_audio_ms == 2500


def test_report_on_my_own_answer_is_404(client, user, auth_headers, session_id):
    answer_on_socket(client, session_id, user.id, text="ok")

    assert report(client, session_id, 1, auth_headers).status_code == 404


def test_report_on_a_missing_turn_is_404(client, auth_headers, session_id):
    assert report(client, session_id, 99, auth_headers).status_code == 404


@pytest.mark.parametrize("ms", [-1, 600_001])
def test_nonsense_numbers_are_rejected(client, auth_headers, session_id, ms):
    assert report(client, session_id, 0, auth_headers, ms=ms).status_code == 422


def test_report_needs_login(client, session_id):
    assert report(client, session_id, 0, headers={}).status_code == 401


def test_other_user_cannot_report(client, db, session_id):
    other = User(email="other@example.com", password_hash="x", name="Other")
    db.add(other)
    db.flush()
    headers = {"Authorization": f"Bearer {create_token(other.id, 'access')}"}

    assert report(client, session_id, 0, headers).status_code == 404


# --- The report ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "values, fraction, expected",
    [
        ([100], 0.9, 100),
        ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9, 9),
        ([10, 9, 8, 7, 6, 5, 4, 3, 2, 1], 0.9, 9),  # order doesn't matter
        ([1, 2, 3], 0.5, 2),
    ],
)
def test_percentile(values, fraction, expected):
    assert percentile(values, fraction) == expected


def test_summary_line_handles_no_measurements():
    assert "no measurements" in summary_line("Whisper", [])


def test_rule_replies_text_is_what_the_report_filters_on():
    """If REPEAT_TEXT changed, the report must keep treating it as a rule reply."""
    assert REPEAT_TEXT in RULE_REPLIES
