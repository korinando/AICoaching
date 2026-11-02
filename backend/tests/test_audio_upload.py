"""POST /sessions/{id}/audio: receiving, decoding and storing a recording (Week 3 Steps 2-4)."""

import io
import wave

import pytest

from app.api import sessions as sessions_api
from app.api.deps import get_audio_storage
from app.core.security import create_token
from app.main import app
from app.models import InterviewSession, User
from app.speech.storage import StorageError
from tests.fakes import FakeAudioStorage, decision

BROWSER_TYPES = {
    "webm": "audio/webm;codecs=opus",  # Chrome
    "mp4": "audio/mp4",  # Safari
    "ogg": "audio/ogg;codecs=opus",  # Firefox (sometimes)
}


@pytest.fixture(autouse=True)
def storage(client) -> FakeAudioStorage:
    """Every test here stores into a dict. test_storage.py covers the real server."""
    fake = FakeAudioStorage()
    app.dependency_overrides[get_audio_storage] = lambda: fake
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


@pytest.mark.parametrize("name", ["webm", "mp4", "ogg"])
def test_every_browser_format_is_decoded(client, auth_headers, session_id, audio_samples, name):
    data = audio_samples[name]

    response = upload(client, session_id, auth_headers, data, BROWSER_TYPES[name])

    assert response.status_code == 200
    body = response.json()
    assert body["size_bytes"] == len(data)
    assert body["content_type"] == BROWSER_TYPES[name]
    assert body["duration_seconds"] == pytest.approx(2.0, abs=0.1)
    # 2 s x 16 000 samples x 2 bytes + a 44-byte header = about 64 KB, whatever came in
    assert body["wav_bytes"] == pytest.approx(64_044, abs=3_200)


def test_recording_is_stored_as_wav_under_the_returned_key(
    client, auth_headers, session_id, audio_samples, storage
):
    response = upload(client, session_id, auth_headers, audio_samples["webm"])

    key = response.json()["audio_key"]
    assert key.startswith(f"sessions/{session_id}/") and key.endswith(".wav")
    data, content_type = storage.files[key]
    assert content_type == "audio/wav"
    with wave.open(io.BytesIO(data)) as w:  # really the converted file, not the original
        assert w.getframerate() == 16_000


def test_two_uploads_never_share_a_key(client, auth_headers, session_id, audio_samples, storage):
    upload(client, session_id, auth_headers, audio_samples["webm"])
    upload(client, session_id, auth_headers, audio_samples["webm"])

    assert len(storage.files) == 2


def test_rejected_uploads_are_not_stored(client, auth_headers, session_id, audio_samples, storage):
    upload(client, session_id, auth_headers, audio_samples["short_webm"])
    upload(client, session_id, auth_headers, b"not really audio" * 100)

    assert storage.files == {}


def test_storage_down_is_503(client, auth_headers, session_id, audio_samples, storage):
    storage.error = StorageError("connection refused")

    response = upload(client, session_id, auth_headers, audio_samples["webm"])

    assert response.status_code == 503


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
