"""Functions the worker runs. The queue stores only this function's name and its arguments, so the
arguments must be small, simple values, like a session id and not a database object."""

from functools import lru_cache
from typing import Any

from sqlalchemy.orm import Session

from app.agent.llm_client import GeminiLLMClient
from app.core.config import get_settings
from app.core.db import get_engine
from app.models import InterviewSession
from app.scoring.scorer import score_session
from app.services.reports import fill_report


@lru_cache
def _llm() -> GeminiLLMClient:
    settings = get_settings()
    return GeminiLLMClient(
        model=settings.llm_model, api_key=settings.gemini_api_key.get_secret_value()
    )


def ping(message: str) -> str:
    """Proves that the worker can run a job and return a result: scripts/check_queue.py."""
    return f"worker got: {message}"


def score_interview(session: InterviewSession) -> dict[str, Any]:
    return score_session(session, _llm())


def generate_report(session_id: int) -> None:
    with Session(get_engine()) as db:
        fill_report(db, session_id, score_interview)
