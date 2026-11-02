"""POST /sessions/{id}/audio: a spoken answer from upload to interviewer reply (Week 3)."""

import io
import wave

import pytest
from sqlalchemy import select

from app.agent.interviewer import REPEAT_TEXT
from app.api import sessions as sessions_api
from app.api.deps import get_audio_storage, get_speech_to_text
from app.api.schemas import MAX_ANSWER_CHARS
from app.core.security import create_token
from app.main import app
from app.models import InterviewSession, Turn, User
from app.speech.storage import StorageError
from app.speech.stt import SpeechToTextError
from tests.fakes import ANSWER, FakeAudioStorage, FakeSpeechToText, decision

BROWSER_TYPES = {
    "webm": "audio/webm;codecs=opus",  # Chrome
    "mp4": "audio/mp4",  # Safari
    "ogg": "audio/ogg;codecs=opus",  # Firefox (sometimes)
}
REPLY = "Why would you add it?"


@pytest.fixture(autouse=True)
def storage(client) -> FakeAudioStorage:
    """Every test here stores into a dict. test_storage.py covers the real server."""
    fake = FakeAudioStorage()
    app.dependency_overrides[get_audio_storage] = lambda: fake
    return fake


@pytest.fixture(autouse=True)
def speech(client) -> FakeSpeechToText:
    """Whisper is replaced by a set text. scripts/check_stt.py covers the real model."""
    fake = FakeSpeechToText()
    app.dependency_overrides[get_speech_to_text] = lambda: fake
    return fake


@pytest.fixture
def session_id(client, auth_headers, fake_llm, template) -> int:
    fake_llm.script.append(decision("next_question", text="Welcome! What is REST?"))
    response = client.post("/sessions", json={"template_id": template.id}, headers=auth_headers)
    return response.json()["id"]


def upload(client, session_id, headers, data, content_type="audio/webm;codecs=opus"):
    # files= sends multipart/form-data, like the browser's FormData: (filename, bytes, type)
    return client.post(
        f"/sessions/{session_id}/audio",
        files={"audio": ("answer", data, content_type)},
        headers=headers,
    )


def turns_in_db(db, session_id) -> list[Turn]:
    return list(
        db.scalars(select(Turn).where(Turn.session_id == session_id).order_by(Turn.turn_index))
    )


# --- The whole path --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["webm", "mp4", "ogg"])
def test_spoken_answer_gets_the_interviewers_reply(
    client, auth_headers, session_id, audio_samples, fake_llm, speech, name
):
    fake_llm.script.append(decision("follow_up", text=REPLY))

    response = upload(client, session_id, auth_headers, audio_samples[name], BROWSER_TYPES[name])

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_progress"
    assert [(t["turn_index"], t["speaker"], t["text"]) for t in body["turns"]] == [
        (1, "candidate", ANSWER),
        (2, "interviewer", REPLY),
    ]
    # Whisper received the normalized audio, whatever format came in.
    with wave.open(io.BytesIO(speech.calls[0])) as w:
        assert w.getframerate() == 16_000
        assert w.getnchannels() == 1


def test_recording_key_is_saved_on_the_candidates_turn(
    client, db, auth_headers, session_id, audio_samples, fake_llm, storage
):
    fake_llm.script.append(decision("follow_up", text=REPLY))

    upload(client, session_id, auth_headers, audio_samples["webm"])

    opening, answer, reply = turns_in_db(db, session_id)
    assert answer.audio_url.startswith(f"sessions/{session_id}/")
    assert opening.audio_url is None and reply.audio_url is None
    data, content_type = storage.files[answer.audio_url]
    assert content_type == "audio/wav"
    with wave.open(io.BytesIO(data)) as w:  # really the converted file, not the original
        assert w.getframerate() == 16_000


def test_two_uploads_never_share_a_key(
    client, auth_headers, session_id, audio_samples, fake_llm, storage
):
    fake_llm.script.extend([decision("follow_up"), decision("follow_up")])

    upload(client, session_id, auth_headers, audio_samples["webm"])
    upload(client, session_id, auth_headers, audio_samples["webm"])

    assert len(storage.files) == 2


def test_typed_answers_have_no_recording(client, db, auth_headers, session_id, fake_llm):
    fake_llm.script.append(decision("follow_up", text=REPLY))

    client.post(f"/sessions/{session_id}/answer", json={"text": ANSWER}, headers=auth_headers)

    assert all(turn.audio_url is None for turn in turns_in_db(db, session_id))


# --- What the transcript contains --------------------------------------------------------------


def test_no_speech_asks_again_without_touching_the_interview(
    client, db, auth_headers, session_id, audio_samples, fake_llm, storage, speech
):
    speech.text = ""
    calls_after_start = len(fake_llm.calls)

    response = upload(client, session_id, auth_headers, audio_samples["webm"])

    assert response.status_code == 422
    assert response.json()["detail"] == "No speech detected. Please try again."
    assert len(fake_llm.calls) == calls_after_start
    assert storage.files == {}
    assert len(turns_in_db(db, session_id)) == 1  # still only the opening question


def test_very_short_transcript_uses_the_week_1_rule(
    client, auth_headers, session_id, audio_samples, fake_llm, speech
):
    """Real speech but under 3 words: the agent's REPEAT_TEXT, with no LLM call."""
    speech.text = "yes"
    calls_after_start = len(fake_llm.calls)

    response = upload(client, session_id, auth_headers, audio_samples["webm"])

    assert response.json()["turns"][-1]["text"] == REPEAT_TEXT
    assert len(fake_llm.calls) == calls_after_start


def test_very_long_transcript_is_cut_to_the_answer_limit(
    client, auth_headers, session_id, audio_samples, fake_llm, speech
):
    speech.text = "word " * MAX_ANSWER_CHARS
    fake_llm.script.append(decision("follow_up"))

    response = upload(client, session_id, auth_headers, audio_samples["webm"])

    assert len(response.json()["turns"][0]["text"]) == MAX_ANSWER_CHARS


# --- Failures ----------------------------------------------------------------------------------


def test_speech_to_text_failure_is_503_and_changes_nothing(
    client, db, auth_headers, session_id, audio_samples, storage, speech
):
    speech.error = SpeechToTextError("model crashed")

    response = upload(client, session_id, auth_headers, audio_samples["webm"])

    assert response.status_code == 503
    assert storage.files == {}
    assert len(turns_in_db(db, session_id)) == 1


def test_storage_down_is_503_and_changes_nothing(
    client, db, auth_headers, session_id, audio_samples, fake_llm, storage
):
    storage.error = StorageError("connection refused")
    calls_after_start = len(fake_llm.calls)

    response = upload(client, session_id, auth_headers, audio_samples["webm"])

    assert response.status_code == 503
    assert len(fake_llm.calls) == calls_after_start
    assert len(turns_in_db(db, session_id)) == 1


def test_rejected_uploads_stop_before_whisper(
    client, auth_headers, session_id, audio_samples, storage, speech
):
    upload(client, session_id, auth_headers, audio_samples["short_webm"])
    upload(client, session_id, auth_headers, b"not really audio" * 100)

    assert speech.calls == []
    assert storage.files == {}


def test_wrong_content_type_is_415(client, auth_headers, session_id, audio_samples):
    response = upload(client, session_id, auth_headers, audio_samples["webm"], "text/plain")

    assert response.status_code == 415


def test_fake_audio_is_415(client, auth_headers, session_id):
    """Claims to be audio (the header is only the client's word), but ffmpeg can't decode it."""
    response = upload(client, session_id, auth_headers, b"not really audio" * 100)

    assert response.status_code == 415
    assert response.json()["detail"] == "Could not read the recording as audio"


def test_too_short_is_422(client, auth_headers, session_id, audio_samples):
    """0.4 s: the server measures the length itself instead of trusting the browser."""
    response = upload(client, session_id, auth_headers, audio_samples["short_webm"])

    assert response.status_code == 422


def test_empty_recording_is_400(client, auth_headers, session_id):
    assert upload(client, session_id, auth_headers, b"").status_code == 400


def test_too_big_is_413(client, auth_headers, session_id, monkeypatch):
    # A small limit for the test, instead of sending 10 MB. Checked before decoding.
    monkeypatch.setattr(sessions_api, "MAX_AUDIO_BYTES", 1000)

    response = upload(client, session_id, auth_headers, b"\x00" * 1001)

    assert response.status_code == 413


def test_missing_file_is_422(client, auth_headers, session_id):
    response = client.post(f"/sessions/{session_id}/audio", headers=auth_headers)

    assert response.status_code == 422


def test_upload_needs_login(client, session_id, audio_samples):
    assert upload(client, session_id, {}, audio_samples["webm"]).status_code == 401


def test_other_users_session_is_404(client, session_id, db, audio_samples):
    """Same ownership rule as the text endpoints (Step 7)."""
    other = User(email="other@example.com", password_hash="x", name="Other")
    db.add(other)
    db.flush()
    headers = {"Authorization": f"Bearer {create_token(other.id, 'access')}"}

    assert upload(client, session_id, headers, audio_samples["webm"]).status_code == 404


def test_finished_interview_is_409(client, auth_headers, session_id, db, audio_samples):
    db.get(InterviewSession, session_id).status = "completed"
    db.flush()

    assert upload(client, session_id, auth_headers, audio_samples["webm"]).status_code == 409
