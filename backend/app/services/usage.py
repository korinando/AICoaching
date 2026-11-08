"""The daily interview limit per user (Week 7 Step 7)."""

from datetime import UTC, date, datetime

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import UsageLimit


class DailyLimitReachedError(Exception):
    def __init__(self, limit: int) -> None:
        super().__init__(
            f"You've used today's {limit} interviews. More are available from midnight UTC."
        )
        self.limit = limit


def daily_session_limit() -> int:
    return get_settings().daily_session_limit


def today() -> date:
    # UTC, so the day is the same whatever server the app runs on.
    return datetime.now(UTC).date()


def take_daily_session(db: Session, user_id: int, day: date | None = None) -> date:
    """Use one of today's interviews, or raise DailyLimitReachedError. Returns the day counted.

    One statement that checks and counts at once, so two requests at the same moment can't both
    slip in under the limit (check first, then count, would let them):
    - no row for today yet: insert one with a count of 1;
    - a row: add 1, but only WHERE the count is still under the limit;
    - RETURNING gives back the new count, or nothing when the WHERE said no.
    Committed at once: holding it in an open transaction during the Gemini call would keep the
    row locked for seconds.
    """
    day = day or today()
    limit = daily_session_limit()
    statement = (
        insert(UsageLimit)
        .values(user_id=user_id, date=day, sessions_count=1)
        .on_conflict_do_update(
            index_elements=[UsageLimit.user_id, UsageLimit.date],
            set_={"sessions_count": UsageLimit.sessions_count + 1},
            where=UsageLimit.sessions_count < limit,
        )
        .returning(UsageLimit.sessions_count)
    )
    count = db.scalar(statement)
    db.commit()
    if count is None:
        raise DailyLimitReachedError(limit)
    return day


def give_back_daily_session(db: Session, user_id: int, day: date) -> None:
    """The interview didn't start after all: it shouldn't use up one of the day's."""
    db.execute(
        update(UsageLimit)
        .where(UsageLimit.user_id == user_id, UsageLimit.date == day, UsageLimit.sessions_count > 0)
        .values(sessions_count=UsageLimit.sessions_count - 1)
    )
    db.commit()
