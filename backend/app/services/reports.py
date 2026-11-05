"""Feedback reports: asking for one when an interview ends, and filling it in (Week 5).

Both are safe to run twice. A job can run again after a retry or a crash, so "running it twice"
has to mean the same as "running it once": still one report, and no second scoring of a ready one.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.exceptions import RedisError
from rq import Queue
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.agent.interviewer import MIN_ANSWER_WORDS
from app.models import FeedbackReport, InterviewSession
from app.scoring.scorer import build_pairs

logger = logging.getLogger(__name__)

# A name and not the function itself: the API only needs to name the job, and the worker imports it.
REPORT_JOB = "app.workers.jobs.generate_report"
# Hearing the recordings again, then Gemini, which has been slow (a 92 s call in Week 4).
JOB_TIMEOUT_S = 600
MAX_ERROR_CHARS = 2000
# A report judges a pattern across the interview, and 1 or 2 answers can't show one. A guess: Week 6
# may show a better number.
MIN_ANSWERS_TO_SCORE = 3

# Takes a finished interview, returns the report's fields. Raises if it can't: see fill_report.
Scorer = Callable[[InterviewSession], dict[str, Any]]


def has_enough_to_score(session: InterviewSession) -> bool:
    """Only answers with real words count, with the same limit as the interviewer's "say more"."""
    pairs = build_pairs(session.turns)
    real_answers = [pair for pair in pairs if len(pair.answer.split()) >= MIN_ANSWER_WORDS]
    return len(real_answers) >= MIN_ANSWERS_TO_SCORE


def queue_report(queue: Queue, session_id: int) -> None:
    """A failure here is only logged: the interview is over and saved, and that matters more.
    The report stays pending, and scripts/retry_reports.py can send it again."""
    try:
        queue.enqueue(REPORT_JOB, session_id, job_timeout=JOB_TIMEOUT_S)
    except RedisError as e:
        logger.warning("Session %s: the report wasn't queued: %s", session_id, e)


def request_report(db: Session, queue: Queue, session_id: int) -> None:
    """The interview has ended: make sure its report exists, and queue the work if it's worth
    scoring. Too short: no job, so no Gemini call is spent on it."""
    enough = has_enough_to_score(db.get(InterviewSession, session_id))
    # ON CONFLICT DO NOTHING: if the row already exists, this quietly changes nothing.
    db.execute(
        insert(FeedbackReport)
        .values(session_id=session_id, status="pending" if enough else "too_short")
        .on_conflict_do_nothing(index_elements=["session_id"])
    )
    # Saved before queueing: the worker must never pick up a job and find no row.
    db.commit()
    if enough:
        queue_report(queue, session_id)


def get_report(db: Session, session_id: int) -> FeedbackReport | None:
    return db.scalar(select(FeedbackReport).where(FeedbackReport.session_id == session_id))


def can_request_report(report: FeedbackReport | None) -> bool:
    """None: never asked for. Failed: can be tried again. Pending past the job's time limit: its
    worker must have died, because the job would have ended by now."""
    if report is None or report.status == "failed":
        return True
    if report.status == "pending":
        return datetime.now(UTC) - report.created_at > timedelta(seconds=JOB_TIMEOUT_S)
    return False


def request_report_again(db: Session, queue: Queue, session_id: int) -> None:
    """Does nothing while one is being made or if it's ready, so a double click can't start a second
    job. A new row and not an update: its created_at starts the wait for a stuck job again."""
    if not can_request_report(get_report(db, session_id)):
        return
    db.execute(delete(FeedbackReport).where(FeedbackReport.session_id == session_id))
    request_report(db, queue, session_id)


def fill_report(db: Session, session_id: int, scorer: Scorer) -> None:
    """The worker's job. A failed scoring is saved on the report and isn't raised: a failed report
    is a normal result that the page can show and someone can retry."""
    report = db.scalar(select(FeedbackReport).where(FeedbackReport.session_id == session_id))
    if report is None or report.status in ("ready", "too_short"):
        return
    session = db.get(InterviewSession, session_id)
    if session.status == "in_progress":
        logger.warning("Session %s is still in progress: not scoring it", session_id)
        return
    try:
        result = scorer(session)
        report.overall_score = result["overall_score"]
        report.scores = result["scores"]
        report.strengths = result["strengths"]
        report.improvements = result["improvements"]
        report.status = "ready"
        report.error = None
        db.commit()
    except Exception as e:
        # Not only scoring errors: any bug here must leave a failed report, not one stuck pending.
        logger.exception("Session %s: the report failed", session_id)
        db.rollback()
        report = db.scalar(select(FeedbackReport).where(FeedbackReport.session_id == session_id))
        report.status = "failed"
        report.error = f"{type(e).__name__}: {e}"[:MAX_ERROR_CHARS]
        db.commit()
