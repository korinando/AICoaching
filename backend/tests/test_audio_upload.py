"""POST /sessions/{id}/audio: receiving a recording (Week 3 Step 2)."""

import pytest

from app.api import sessions as sessions_api
from app.core.security import create_token
from app.models import InterviewSession, User
from tests.fakes import decision

# Not real audio: Step 2 only checks the upload itself. Real audio is needed from Step 3.
FAKE_WEBM = b"\x1aE\xdf\xa3" + b"\x00" * 2000


@pytest.fixture
def session_id(client, auth_headers, fake_llm, template) -> int:
    fake_llm.script.append(decision("next_question", text="Welcome! What is REST?"))
    response = client.post("/sessions", json={"template_id": template.id}, headers=auth_headers)
    return response.json()["id"]


def upload(client, session_id, headers, data=FAKE_WEBM, content_type="audio/webm;codecs=opus"):
    # files= sends multipart/form-data, like the browser's FormData: (filename, bytes, type)
    return client.post(
        f"/sessions/{session_id}/audio",
        files={"audio": ("answer.webm", data, content_type)},
        headers=headers,
    )


def test_upload_reports_what_arrived(client, auth_headers, session_id):
    response = upload(client, session_id, auth_headers)

    assert response.status_code == 200
    assert response.json() == {
        "size_bytes": len(FAKE_WEBM),
        "content_type": "audio/webm;codecs=opus",
    }


def test_safari_format_is_accepted(client, auth_headers, session_id):
    assert upload(client, session_id, auth_headers, content_type="audio/mp4").status_code == 200


def test_not_audio_is_415(client, auth_headers, session_id):
    response = upload(client, session_id, auth_headers, content_type="text/plain")

    assert response.status_code == 415


def test_empty_recording_is_400(client, auth_headers, session_id):
    assert upload(client, session_id, auth_headers, data=b"").status_code == 400


def test_too_big_is_413(client, auth_headers, session_id, monkeypatch):
    # A small limit for the test, instead of sending 10 MB.
    monkeypatch.setattr(sessions_api, "MAX_AUDIO_BYTES", 1000)

    response = upload(client, session_id, auth_headers, data=b"\x00" * 1001)

    assert response.status_code == 413


def test_missing_file_is_422(client, auth_headers, session_id):
    response = client.post(f"/sessions/{session_id}/audio", headers=auth_headers)

    assert response.status_code == 422


def test_upload_needs_login(client, session_id):
    assert upload(client, session_id, headers={}).status_code == 401


def test_other_users_session_is_404(client, session_id, db):
    """Same ownership rule as the text endpoints (Step 7)."""
    other = User(email="other@example.com", password_hash="x", name="Other")
    db.add(other)
    db.flush()
    headers = {"Authorization": f"Bearer {create_token(other.id, 'access')}"}

    assert upload(client, session_id, headers).status_code == 404


def test_finished_interview_is_409(client, auth_headers, session_id, db):
    db.get(InterviewSession, session_id).status = "completed"
    db.flush()

    assert upload(client, session_id, auth_headers).status_code == 409
