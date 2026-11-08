"""Importing this package registers every model on Base.metadata (Alembic needs them all)."""

from app.models.base import Base
from app.models.feedback_report import REPORT_STATUSES, FeedbackReport
from app.models.interview_session import SESSION_STATUSES, InterviewSession
from app.models.template import InterviewTemplate
from app.models.turn import Turn
from app.models.usage_limit import UsageLimit
from app.models.user import User

__all__ = [
    "REPORT_STATUSES",
    "SESSION_STATUSES",
    "Base",
    "FeedbackReport",
    "InterviewSession",
    "InterviewTemplate",
    "Turn",
    "UsageLimit",
    "User",
]
