"""CORS: which web pages may call the API from a browser. No database needed."""

from fastapi.testclient import TestClient

from app.main import app

FRONTEND = "http://localhost:3000"


def preflight(origin: str, method: str = "POST", headers: str = "authorization,content-type"):
    """What a browser sends before a cross-origin request: "may I send this?" """
    return TestClient(app).options(
        "/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
        },
    )


def test_frontend_preflight_is_allowed():
    response = preflight(FRONTEND)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND


def test_unknown_site_is_not_allowed():
    """A page on another site gets no allow header, so its browser blocks the response."""
    response = preflight("https://evil.example.com")

    assert "access-control-allow-origin" not in response.headers


def test_unlisted_method_is_not_allowed():
    """Starlette still sends the origin header here, but the browser refuses anyway: a
    preflight must answer 2xx, and DELETE isn't in the allowed methods."""
    response = preflight(FRONTEND, method="DELETE")

    assert response.status_code == 400
    assert "DELETE" not in response.headers["access-control-allow-methods"]


def test_normal_response_carries_the_header():
    """After the preflight, the real response must allow the origin too, or the page can't read it."""
    response = TestClient(app).get("/health", headers={"Origin": FRONTEND})

    assert response.headers["access-control-allow-origin"] == FRONTEND
