from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.db import get_db
from app.main import app


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
