"""Admin-only endpoints, for the debug panel. Every route here needs an ADMIN_EMAILS account:
the frontend hides the button from everyone else, but this check is the one that protects them."""

import os

from fastapi import APIRouter, Depends, HTTPException, status
from redis.exceptions import RedisError
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.api.deps import DB, ReportQueueDep, SettingsDep, get_admin_user
from app.api.schemas import DebugInfoOut, TurnTimingOut
from app.models import InterviewSession, Turn

# dependencies= on the router: no route added here later can forget the check.
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_admin_user)])


@router.get("/debug")
def debug_info(db: DB, queue: ReportQueueDep, settings: SettingsDep) -> DebugInfoOut:
    """Which code and models this server runs, and whether the database and Redis answer."""
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except OperationalError:  # the same check as /health/ready
        database = "unavailable"
    try:
        queue.connection.ping()
        redis, queued = "ok", queue.count
    except RedisError:  # the panel is for finding problems: report one, don't become one
        redis, queued = "unavailable", None
    return DebugInfoOut(
        # Railway sets this to the deployed commit. Not set when running on your computer.
        commit=os.environ.get("RAILWAY_GIT_COMMIT_SHA"),
        llm_model=settings.llm_model,
        whisper_model=settings.whisper_model,
        scoring_whisper_model=settings.scoring_whisper_model,
        piper_voice=settings.piper_voice,
        daily_session_limit=settings.daily_session_limit,
        database=database,
        redis=redis,
        queued_reports=queued,
    )


@router.get("/sessions/{session_id}/timings")
def session_timings(session_id: int, db: DB) -> list[TurnTimingOut]:
    """Where the time went in each turn of any user's interview, oldest first. Any user's, on
    purpose: an admin looks into someone's "it was slow" report."""
    if db.get(InterviewSession, session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    turns = db.scalars(select(Turn).where(Turn.session_id == session_id).order_by(Turn.turn_index))
    return [TurnTimingOut.model_validate(turn) for turn in turns]
