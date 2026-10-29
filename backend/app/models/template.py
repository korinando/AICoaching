from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class InterviewTemplate(Base):
    """A row per entry in agent/templates.json, copied in by scripts/seed_templates.py."""

    __tablename__ = "interview_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The key from templates.json ("junior_backend"): a stable name the seed script uses
    # to find the row again, so re-running the seed updates instead of duplicating.
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    role: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(50))
    interview_type: Mapped[str] = mapped_column(String(50))
    # JSONB: a list stored in one column. Topics are always read together with their
    # template and never searched on their own, so a separate table would add nothing.
    topics: Mapped[list[str]] = mapped_column(JSONB)
    max_main_questions: Mapped[int]
    max_follow_ups: Mapped[int]
