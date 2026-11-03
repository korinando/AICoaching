from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:  # only for the editor/type checker; avoids a circular import at runtime
    from app.models.interview_session import InterviewSession


class Turn(Base):
    """One message in an interview: the interviewer's question or the candidate's answer."""

    __tablename__ = "turns"
    __table_args__ = (
        # Two turns can't share a position in the same session. This also creates an index
        # starting with session_id, which "all turns of a session" uses, so session_id
        # needs no index of its own.
        UniqueConstraint("session_id", "turn_index"),
        CheckConstraint("speaker IN ('interviewer', 'candidate')", name="speaker_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"))
    turn_index: Mapped[int]
    speaker: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    # Voice (Week 3) and latency (Week 3-4) columns exist from day one, as the plan says,
    # so adding voice doesn't need a migration. NULL while the interview is text only.
    audio_url: Mapped[str | None] = mapped_column(String(500))
    stt_ms: Mapped[int | None]
    llm_ms: Mapped[int | None]
    tts_ms: Mapped[int | None]
    # Latency of one reply, all on the interviewer's turn (Week 3 Step 7). Whisper, the
    # interviewer, Piper, then the whole server side from receiving the upload to audio ready.
    total_latency_ms: Mapped[int | None]
    # Measured by the browser: end of my speech -> the reply starts playing. Also counts the
    # upload, the audio download and the browser, which the server can't see.
    first_audio_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["InterviewSession"] = relationship(back_populates="turns")

    @property
    def has_audio(self) -> bool:
        """What the API tells the browser. The storage key itself stays private."""
        return self.audio_url is not None
