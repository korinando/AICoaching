"""A spoken answer from recording to interviewer reply, whatever format the browser records in."""

import io
import wave

import pytest
from sqlalchemy import select

from app.agent.interviewer import REPEAT_TEXT
from app.api.deps import get_speech_to_text
from app.api.schemas import MAX_ANSWER_CHARS
from app.main import app
from app.models import Turn
from app.services import recordings
from app.speech.storage import StorageError
from app.speech.stt import SpeechToTextError
from tests.fakes import ANSWER, FakeSpeechToText, decision, streamed
from tests.ws_client import answer_on_socket

REPLY = "Why would you add it?"


@pytest.fixture(autouse=True)
def speech(client) -> FakeSpeechToText:
    """Whisper is replaced by a set text. scripts/check_stt.py covers the real model."""
    fake = FakeSpeechToText()
    app.dependency_overrides[get_speech_to_text] = lambda: fake
    return fake


@pytest.fixture
def session_id(client, auth_headers, fake_llm, template, storage) -> int:
    fake_llm.script.append(decision("next_question", text="Welcome! What is REST?"))
    response = client.post("/sessions", json={"template_id": template.id}, headers=auth_headers)
    storage.files.clear()  # forget the opening question's audio: tests count what they cause
    return response.json()["id"]


def turns_in_db(db, session_id) -> list[Turn]:
    db.expire_all()
    return list(
        db.scalars(select(Turn).where(Turn.session_id == session_id).order_by(Turn.turn_index))
    )


# --- The whole path --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["webm", "mp4", "ogg"])  # Chrome, Safari, Firefox (sometimes)
def test_spoken_answer_gets_the_interviewers_reply(
    client, db, user, session_id, audio_samples, fake_llm, speech, name
):
    fake_llm.script.append(streamed("follow_up", REPLY))

    messages = answer_on_socket(client, session_id, user.id, recording=audio_samples[name])

    assert messages[0] == {"type": "transcript", "turn_index": 1, "text": ANSWER}
    assert messages[1]["text"] == REPLY
    assert [(t.speaker, t.text) for t in turns_in_db(db, session_id)[1:]] == [
        ("candidate", ANSWER),
        ("interviewer", REPLY),
    ]
    # Whisper received the normalized audio, whatever format came in.
    with wave.open(io.BytesIO(speech.calls[0])) as w:
        assert w.getframerate() == 16_000
        assert w.getnchannels() == 1


def test_recording_key_is_saved_on_the_candidates_turn(
    client, db, user, session_id, audio_samples, fake_llm, storage
):
    fake_llm.script.append(streamed("follow_up", REPLY))

    answer_on_socket(client, session_id, user.id, recording=audio_samples["webm"])

    _opening, answer, _reply = turns_in_db(db, session_id)
    assert answer.audio_url.startswith(f"sessions/{session_id}/")
    data, content_type = storage.files[answer.audio_url]
    assert content_type == "audio/wav"
    with wave.open(io.BytesIO(data)) as w:  # really the converted file, not the original
        assert w.getframerate() == 16_000


def test_two_recordings_never_share_a_key(
    client, user, session_id, audio_samples, fake_llm, storage
):
    fake_llm.script.extend([streamed("follow_up"), streamed("follow_up")])

    answer_on_socket(client, session_id, user.id, recording=audio_samples["webm"])
    answer_on_socket(client, session_id, user.id, recording=audio_samples["webm"])

    assert len(storage.files) == 4  # 2 recordings + 2 spoken replies, nothing overwritten


def test_typed_answers_have_no_recording(client, db, user, session_id, fake_llm):
    fake_llm.script.append(streamed("follow_up", REPLY))

    answer_on_socket(client, session_id, user.id, text=ANSWER)

    _opening, answer, _reply = turns_in_db(db, session_id)
    assert answer.audio_url is None


# --- What the transcript contains --------------------------------------------------------------


def test_no_speech_asks_again_without_touching_the_interview(
    client, db, user, session_id, audio_samples, fake_llm, storage, speech
):
    speech.text = ""
    calls_after_start = len(fake_llm.calls)

    [error] = answer_on_socket(client, session_id, user.id, recording=audio_samples["webm"])

    assert error["code"] == "no_speech"
    assert error["message"] == "No speech detected. Please try again."
    assert len(fake_llm.calls) == calls_after_start
    assert storage.files == {}
    assert len(turns_in_db(db, session_id)) == 1  # still only the opening question


def test_very_short_transcript_uses_the_week_1_rule(
    client, user, session_id, audio_samples, fake_llm, speech
):
    """Real speech but under 3 words: the agent's REPEAT_TEXT, with no LLM call."""
    speech.text = "yes"
    calls_after_start = len(fake_llm.calls)

    messages = answer_on_socket(client, session_id, user.id, recording=audio_samples["webm"])

    assert messages[1]["text"] == REPEAT_TEXT
    assert len(fake_llm.calls) == calls_after_start


def test_very_long_transcript_is_cut_to_the_answer_limit(
    client, user, session_id, audio_samples, fake_llm, speech
):
    speech.text = "word " * MAX_ANSWER_CHARS
    fake_llm.script.append(streamed("follow_up"))

    messages = answer_on_socket(client, session_id, user.id, recording=audio_samples["webm"])

    assert len(messages[0]["text"]) == MAX_ANSWER_CHARS


# --- Failures ----------------------------------------------------------------------------------


def test_speech_to_text_failure_changes_nothing(
    client, db, user, session_id, audio_samples, storage, speech
):
    speech.error = SpeechToTextError("model crashed")

    [error] = answer_on_socket(client, session_id, user.id, recording=audio_samples["webm"])

    assert error["code"] == "server_error"
    assert storage.files == {}
    assert len(turns_in_db(db, session_id)) == 1


def test_storage_down_changes_nothing(
    client, db, user, session_id, audio_samples, fake_llm, storage
):
    storage.error = StorageError("connection refused")
    calls_after_start = len(fake_llm.calls)

    [error] = answer_on_socket(client, session_id, user.id, recording=audio_samples["webm"])

    assert error["code"] == "server_error"
    assert len(fake_llm.calls) == calls_after_start
    assert len(turns_in_db(db, session_id)) == 1


def test_rejected_recordings_stop_before_whisper(
    client, user, session_id, audio_samples, storage, speech
):
    answer_on_socket(client, session_id, user.id, recording=audio_samples["short_webm"])
    answer_on_socket(client, session_id, user.id, recording=b"not really audio" * 100)

    assert speech.calls == []
    assert storage.files == {}


def test_fake_audio_is_invalid(client, user, session_id):
    """ffmpeg decoding it is the real proof that a recording is audio."""
    [error] = answer_on_socket(client, session_id, user.id, recording=b"not really audio" * 100)

    assert error["code"] == "invalid_audio"
    assert error["message"] == "Could not read the recording as audio"


def test_too_short_is_invalid(client, user, session_id, audio_samples):
    """0.4 s: the server measures the length itself instead of trusting the browser."""
    [error] = answer_on_socket(client, session_id, user.id, recording=audio_samples["short_webm"])

    assert error["code"] == "invalid_audio"


def test_empty_recording_is_invalid(client, user, session_id):
    [error] = answer_on_socket(client, session_id, user.id, recording=b"")

    assert error["code"] == "invalid_audio"


def test_too_big_is_invalid(client, user, session_id, monkeypatch):
    # A small limit for the test, instead of sending 10 MB. Checked before decoding.
    monkeypatch.setattr(recordings, "MAX_AUDIO_BYTES", 1000)

    [error] = answer_on_socket(client, session_id, user.id, recording=b"\x00" * 1001)

    assert error["code"] == "invalid_audio"
