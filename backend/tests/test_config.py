import pytest
from pydantic import ValidationError

from app.core.config import Settings

GOOD_ENV = {
    "DATABASE_URL": "postgresql+psycopg://user:pw@localhost:5433/test",
    "JWT_SECRET": "x" * 32,
    "GEMINI_API_KEY": "fake-key",
    "S3_ACCESS_KEY": "fake-access",
    "S3_SECRET_KEY": "fake-secret",
}


@pytest.fixture
def env(monkeypatch):
    """Set known env vars for one test; monkeypatch undoes them afterwards."""
    for name, value in GOOD_ENV.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


def load() -> Settings:
    # _env_file=None: ignore my real backend/.env, so tests only see what they set.
    return Settings(_env_file=None)


def test_settings_read_from_env(env):
    settings = load()
    assert settings.database_url == GOOD_ENV["DATABASE_URL"]
    assert settings.llm_model == "gemini-3.5-flash-lite"  # default when not set


def test_missing_required_setting_fails(env):
    """Fail fast: no DATABASE_URL means the app can't start, with the field name in the error."""
    env.delenv("DATABASE_URL")
    with pytest.raises(ValidationError, match="database_url"):
        load()


def test_short_jwt_secret_is_rejected(env):
    """A short secret can be guessed, and anyone who guesses it can forge logins."""
    env.setenv("JWT_SECRET", "secret")
    with pytest.raises(ValidationError, match="jwt_secret"):
        load()


def test_secrets_are_hidden_when_printed(env):
    settings = load()
    assert "fake-key" not in repr(settings)
    assert "fake-secret" not in repr(settings)
    assert settings.gemini_api_key.get_secret_value() == "fake-key"


@pytest.mark.parametrize(
    "given",
    [
        "postgresql://user:pw@db.internal:5432/railway",  # what hosting platforms usually give
        "postgres://user:pw@db.internal:5432/railway",  # an older spelling some still use
        "postgresql+psycopg://user:pw@db.internal:5432/railway",  # already right: unchanged
    ],
)
def test_database_url_always_uses_the_psycopg_driver(env, given):
    """SQLAlchemy reads plain postgresql:// as "use psycopg2", which isn't installed (we use
    psycopg 3), so the app would crash at the first query on the hosting platform."""
    env.setenv("DATABASE_URL", given)

    assert load().database_url == "postgresql+psycopg://user:pw@db.internal:5432/railway"
