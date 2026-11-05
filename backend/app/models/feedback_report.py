from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

REPORT_STATUSES = ("pending", "ready", "failed")


class FeedbackReport(Base):
    """The report on one finished interview. Empty until the worker has scored it (Week 5)."""

    __tablename__ = "feedback_reports"
    __table_args__ = (CheckConstraint(f"status IN {REPORT_STATUSES}", name="status_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # unique: the database itself guarantees one report per interview, however many jobs run.
    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    overall_score: Mapped[float | None] = mapped_column(Float)
    scores: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    strengths: Mapped[list[str] | None] = mapped_column(JSONB)
    improvements: Mapped[list[str] | None] = mapped_column(JSONB)
    per_question: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    # Why the last try failed, so it can be looked at and tried again.
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
