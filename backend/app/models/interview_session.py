# Not "session.py": SQLAlchemy's own database Session would be easy to confuse with it.
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:  # only for the editor/type checker; avoids a circular import at runtime
    from app.models.template import InterviewTemplate
    from app.models.turn import Turn
    from app.models.user import User

SESSION_STATUSES = ("in_progress", "completed", "abandoned")


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    # A plain string column plus a check, instead of a Postgres ENUM type: adding a status
    # later is a one-line migration, while changing a Postgres ENUM is awkward.
    __table_args__ = (CheckConstraint(f"status IN {SESSION_STATUSES}", name="status_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # ondelete="CASCADE": deleting a user deletes their sessions too, done by Postgres.
    # index=True: "list my sessions" filters on user_id, so look it up fast.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("interview_templates.id"))
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    # The whole InterviewState from Week 1 (state.model_dump(mode="json")). Saved after
    # every turn, so an interview can continue after a server restart (Step 5).
    agent_state: Mapped[dict[str, Any]] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="sessions")
    template: Mapped["InterviewTemplate"] = relationship()
    # order_by: session.turns always comes back in conversation order.
    turns: Mapped[list["Turn"]] = relationship(
        back_populates="session", order_by="Turn.turn_index", cascade="all, delete-orphan"
    )
