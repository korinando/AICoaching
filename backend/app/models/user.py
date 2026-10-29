from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:  # only for the editor/type checker; avoids a circular import at runtime
    from app.models.interview_session import InterviewSession


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # unique=True: the database itself refuses a second account with the same email,
    # even if two register requests arrive at the same moment.
    email: Mapped[str] = mapped_column(String(255), unique=True)
    # Never the password itself: a one-way hash (Step 4).
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    # server_default: Postgres fills in the time, so it's correct even for rows not
    # inserted through Python. timezone=True stores UTC, avoiding time zone bugs.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sessions: Mapped[list["InterviewSession"]] = relationship(back_populates="user")
