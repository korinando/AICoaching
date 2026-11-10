"""App settings, read from environment variables (or backend/.env in development)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env, found from this file's location, so it works whatever folder you start in.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
WHISPER_MODELS_DIR = Path(__file__).resolve().parents[2] / "whisper_models"


class Settings(BaseSettings):
    """Each field is read from the env var with the same name in capitals (database_url ->
    DATABASE_URL). A real environment variable wins over the .env file.
    A required field that is missing stops the app at startup with a clear error."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    database_url: str

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, url: str) -> str:
        """Hosting platforms give postgresql:// (or postgres://), which SQLAlchemy reads as
        "use psycopg2". This app uses psycopg 3, so name it, and the platform's value works as is."""
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url

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
    # Only for reports: the worker hears the recordings again, when nobody is waiting. turbo made
    # the most sense of my real recordings, and is about 3x slower than small.en.
    scoring_whisper_model: str = "turbo"
    # Next to the project and not in the shared Hugging Face folder on C:. A model that isn't here
    # is downloaded here. The worker in Docker reads this same folder.
    whisper_models_dir: Path = WHISPER_MODELS_DIR
    # A file in backend/voices/, downloaded with: uv run python -m piper.download_voices
    piper_voice: str = "en_US-lessac-medium"
    # Monitoring (Week 7 Step 6). JSON log lines in production (the Dockerfile turns it on);
    # readable text in development. Errors go to Sentry only when its DSN is set, on Railway.
    log_json: bool = False
    sentry_dsn: SecretStr = SecretStr("")
    # Cost protection (Week 7 Step 7). Every turn of an interview calls 3 paid services, so one
    # account may start this many interviews per day (UTC).
    daily_session_limit: int = Field(default=5, ge=1)
    # The header in which a trusted proxy puts the visitor's real address. Empty: there's no
    # proxy, use the connection's address. On Railway: X-Real-IP.
    proxy_ip_header: str = ""
    # Accounts that may see the debug panel and call /admin/*. JSON, like CORS_ORIGINS:
    # ADMIN_EMAILS='["me@example.com"]'. Empty: nobody is an admin.
    admin_emails: list[str] = []

    def is_admin(self, email: str) -> bool:
        """Emails are compared without case: Me@x.com and me@x.com are the same inbox."""
        return email.lower() in {e.lower() for e in self.admin_emails}


@lru_cache
def get_settings() -> Settings:
    """Read the settings once and reuse them. Used as a FastAPI dependency from Step 4."""
    return Settings()
