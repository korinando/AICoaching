"""The /auth endpoints, through HTTP, against the ai_coach_test database."""

import pytest

from app.core.security import create_token

EMAIL = "an@example.com"
PASSWORD = "a-good-password"


def register(client, email=EMAIL, password=PASSWORD, name="An"):
    return client.post("/auth/register", json={"email": email, "password": password, "name": name})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Register ----------------------------------------------------------------------------------


def test_register_creates_user(client):
    response = register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == EMAIL
    assert "password" not in body and "password_hash" not in body  # never sent back


def test_register_same_email_twice_is_409(client):
    register(client)
    response = register(client, email=EMAIL.upper())  # case doesn't matter

    assert response.status_code == 409


@pytest.mark.parametrize(
    "email, password",
    [
        ("not-an-email", PASSWORD),
        (EMAIL, "short"),
        (EMAIL, "x" * 129),
    ],
)
def test_register_rejects_bad_input(client, email, password):
    """422 = Pydantic rejected the body before our code ran."""
    assert register(client, email=email, password=password).status_code == 422


# --- Login -------------------------------------------------------------------------------------


def test_login_returns_tokens(client):
    register(client)

    response = login(client, email=EMAIL.upper())

    assert response.status_code == 200
    assert {"access_token", "refresh_token"} <= set(response.json())


@pytest.mark.parametrize("email, password", [(EMAIL, "wrong-password"), ("nobody@x.com", PASSWORD)])
def test_login_failure_never_says_which_part_was_wrong(client, email, password):
    """Same 401 and message for a wrong password and an unknown email."""
    register(client)

    response = login(client, email=email, password=password)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


# --- /auth/me (get_current_user) ---------------------------------------------------------------


def test_me_with_access_token(client):
    register(client)
    token = login(client).json()["access_token"]

    response = client.get("/auth/me", headers=auth_header(token))

    assert response.status_code == 200
    assert response.json()["email"] == EMAIL


@pytest.mark.parametrize(
    "headers",
    [
        {},  # no header
        {"Authorization": "Bearer not-a-token"},
        {"Authorization": "Basic abc"},  # wrong scheme
    ],
)
def test_me_without_valid_token_is_401(client, headers):
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_me_rejects_refresh_token(client):
    register(client)
    refresh_token = login(client).json()["refresh_token"]

    assert client.get("/auth/me", headers=auth_header(refresh_token)).status_code == 401


def test_me_for_deleted_user_is_401(client):
    """A token for a user id that doesn't exist (e.g. account deleted) must not work."""
    assert (
        client.get("/auth/me", headers=auth_header(create_token(999_999, "access"))).status_code
        == 401
    )


# --- Refresh -----------------------------------------------------------------------------------


def test_refresh_gives_working_tokens(client):
    register(client)
    refresh_token = login(client).json()["refresh_token"]

    response = client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    new_access = response.json()["access_token"]
    assert client.get("/auth/me", headers=auth_header(new_access)).status_code == 200


def test_refresh_rejects_access_token(client):
    register(client)
    access_token = login(client).json()["access_token"]

    response = client.post("/auth/refresh", json={"refresh_token": access_token})

    assert response.status_code == 401
