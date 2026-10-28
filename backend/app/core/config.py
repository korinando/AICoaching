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


@lru_cache
def get_settings() -> Settings:
    """Read the settings once and reuse them. Used as a FastAPI dependency from Step 4."""
    return Settings()
