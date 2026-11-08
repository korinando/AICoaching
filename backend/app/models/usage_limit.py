from datetime import date

from sqlalchemy import Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UsageLimit(Base):
    """How many interviews one user started on one day (UTC). Week 7 Step 7.

    Its own table, not a count of interview_sessions: a count would go down if sessions are ever
    deleted (the plan's privacy option), and deleting would then hand out new interviews.
    """

    __tablename__ = "usage_limits"

    # The pair is the key: one row per user per day, which the counting relies on.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    sessions_count: Mapped[int] = mapped_column(default=0)
