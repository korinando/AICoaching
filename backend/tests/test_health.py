from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import main
from app.core.db import get_db
from app.main import app, load_speech_models
from tests.fakes import FakeSpeechToText, FakeTextToSpeech


def test_health_returns_ok():
    """TestClient calls the app in-process: no server, no network, no port."""
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class DatabaseIsDown:
    """Stands in for a Session when the database can't be reached."""

    def execute(self, *_args):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    def scalar(self, *_args):
        raise OperationalError("SELECT", {}, Exception("connection refused"))


def test_ready_when_the_database_answers(client):
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_is_503_when_the_database_is_down(client):
    app.dependency_overrides[get_db] = DatabaseIsDown

    assert client.get("/health/ready").status_code == 503


def test_health_stays_ok_when_the_database_is_down(client):
    """Restarting this server wouldn't fix the database, so liveness must not depend on it."""
    app.dependency_overrides[get_db] = DatabaseIsDown

    assert client.get("/health").status_code == 200


def test_login_says_the_database_is_down_instead_of_a_500(client):
    app.dependency_overrides[get_db] = DatabaseIsDown

    response = client.post(
        "/auth/login", json={"email": "a@example.com", "password": "not-a-real-password"}
    )

    assert response.status_code == 503
    assert "Database unavailable" in response.json()["detail"]


def test_speech_models_are_loaded_at_startup(monkeypatch):
    loaded = []

    class Voice(FakeTextToSpeech):
        def load(self):
            loaded.append("voice")

    class Whisper(FakeSpeechToText):
        def load(self):
            loaded.append("whisper")

    monkeypatch.setattr(main, "get_text_to_speech", Voice)
    monkeypatch.setattr(main, "get_speech_to_text", Whisper)

    load_speech_models()

    assert loaded == ["voice", "whisper"]


def test_a_model_that_fails_to_load_does_not_stop_the_server_or_the_other(monkeypatch):
    voice = FakeTextToSpeech()
    voice.error = FileNotFoundError("voice file missing")
    whisper = FakeSpeechToText()
    whisper.load = lambda: whisper.calls.append(b"loaded")
    monkeypatch.setattr(main, "get_text_to_speech", lambda: voice)
    monkeypatch.setattr(main, "get_speech_to_text", lambda: whisper)

    load_speech_models()

    assert whisper.calls == [b"loaded"]
