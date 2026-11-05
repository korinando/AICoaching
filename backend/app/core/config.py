"""App settings, read from environment variables (or backend/.env in development)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env, found from this file's location, so it works whatever folder you start in.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Each field is read from the env var with the same name in capitals (database_url ->
    DATABASE_URL). A real environment variable wins over the .env file.
    A required field that is missing stops the app at startup with a clear error."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    database_url: str
    # SecretStr hides the value in print/logs/tracebacks: it shows as '**********'.
    # Read the real value with .get_secret_value() only where it's needed.
    jwt_secret: SecretStr = Field(min_length=32)
    gemini_api_key: SecretStr
    llm_model: str = "gemini-3.5-flash-lite"
    # Short access tokens limit the damage if one leaks; the refresh token gets new ones.
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    # Web pages (origins) that may call this API from a browser. Production sets its own,
    # as JSON in the env var: CORS_ORIGINS='["https://coach.example.com"]'
    cors_origins: list[str] = ["http://localhost:3000"]
    # Recordings storage: anything that speaks the S3 API (SeaweedFS here, real S3 later).
    s3_access_key: SecretStr
    s3_secret_key: SecretStr
    s3_endpoint_url: str = "http://127.0.0.1:8333"
    s3_bucket: str = "ai-coach-recordings"
    # The job queue. 127.0.0.1 and not localhost, for the same reason as storage.
    redis_url: str = "redis://127.0.0.1:6379/0"
    # base.en: English only, about 140 MB. Bigger (small.en) is more accurate but slower.
    whisper_model: str = "base.en"
    # Only for reports: the worker hears the recordings again, when nobody is waiting.
    scoring_whisper_model: str = "small.en"
    # A file in backend/voices/, downloaded with: uv run python -m piper.download_voices
    piper_voice: str = "en_US-lessac-medium"


@lru_cache
def get_settings() -> Settings:
    """Read the settings once and reuse them. Used as a FastAPI dependency from Step 4."""
    return Settings()
