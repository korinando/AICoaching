from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    """TestClient calls the app in-process: no server, no network, no port."""
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
