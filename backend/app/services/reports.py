"""Feedback reports: asking for one when an interview ends, and filling it in (Week 5).

Both are safe to run twice. A job can run again after a retry or a crash, so "running it twice"
has to mean the same as "running it once": still one report, and no second scoring of a ready one.
"""

import logging
from collections.abc import Callable
from typing import Any

from redis.exceptions import RedisError
from rq import Queue
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import FeedbackReport, InterviewSession

logger = logging.getLogger(__name__)

# A name and not the function itself: the API only needs to name the job, and the worker imports it.
REPORT_JOB = "app.workers.jobs.generate_report"
# Hearing the recordings again, then Gemini, which has been slow (a 92 s call in Week 4).
JOB_TIMEOUT_S = 600
MAX_ERROR_CHARS = 2000

# Takes a finished interview, returns the report's fields. Raises if it can't: see fill_report.
Scorer = Callable[[InterviewSession], dict[str, Any]]


def queue_report(queue: Queue, session_id: int) -> None:
    """A failure here is only logged: the interview is over and saved, and that matters more.
    The report stays pending, and scripts/retry_reports.py can send it again."""
    try:
        queue.enqueue(REPORT_JOB, session_id, job_timeout=JOB_TIMEOUT_S)
    except RedisError as e:
        logger.warning("Session %s: the report wasn't queued: %s", session_id, e)


def request_report(db: Session, queue: Queue, session_id: int) -> None:
    """The interview has ended: make sure its report exists, and queue the work."""
    # ON CONFLICT DO NOTHING: if the row already exists, this quietly changes nothing.
    db.execute(
        insert(FeedbackReport)
        .values(session_id=session_id, status="pending")
        .on_conflict_do_nothing(index_elements=["session_id"])
    )
    # Saved before queueing: the worker must never pick up a job and find no row.
    db.commit()
    queue_report(queue, session_id)


def fill_report(db: Session, session_id: int, scorer: Scorer) -> None:
    """The worker's job. A failed scoring is saved on the report and isn't raised: a failed report
    is a normal result that the page can show and someone can retry."""
    report = db.scalar(select(FeedbackReport).where(FeedbackReport.session_id == session_id))
    if report is None or report.status == "ready":
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
