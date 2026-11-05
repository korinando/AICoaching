"""Functions the worker runs. The queue stores only this function's name and its arguments, so the
arguments must be small, simple values, like a session id and not a database object."""

from typing import Any

from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.models import InterviewSession
from app.services.reports import fill_report


def ping(message: str) -> str:
    """Proves that the worker can run a job and return a result: scripts/check_queue.py."""
    return f"worker got: {message}"


def score_interview(session: InterviewSession) -> dict[str, Any]:
    """A placeholder until the scoring module exists (app/scoring/, Week 5 Step 3)."""
    raise NotImplementedError("Scoring isn't written yet (Week 5 Step 3)")


def generate_report(session_id: int) -> None:
    with Session(get_engine()) as db:
        fill_report(db, session_id, score_interview)
