"""Better transcripts for scoring: the worker hears the recordings again with a bigger model.

During the interview, speed matters, so base.en listens. In a background job nobody is waiting, so
a bigger model can take its time, and the report judges closer to what was really said. The saved
turns don't change: this is a copy, used only for scoring.

The question isn't given to Whisper as a hint. It fixed some terms, but it also put the question's
words in the candidate's mouth, which would give credit for things they never said.
"""

import logging
from dataclasses import dataclass

from app.models import InterviewSession, InterviewTemplate
from app.speech.storage import AudioStorage, StorageError
from app.speech.stt import SpeechToText, SpeechToTextError

logger = logging.getLogger(__name__)


@dataclass
class ScoringTurn:
    speaker: str
    text: str


@dataclass
class ScoringSession:
    """What the scorer reads from a session, with the better text in it."""

    turns: list[ScoringTurn]
    template: InterviewTemplate


def _better_text(turn, stt: SpeechToText, storage: AudioStorage) -> str:
    """A failure only costs this answer its better text: the saved one can still be scored."""
    if turn.speaker != "candidate" or turn.audio_url is None:
        return turn.text
    try:
        # Empty if the bigger model hears no speech: the saved text is better than nothing.
        return stt.transcribe(storage.load(turn.audio_url)) or turn.text
    except (StorageError, SpeechToTextError) as e:
        logger.warning("Turn %s keeps its saved text: %s", turn.turn_index, e)
        return turn.text


def with_better_transcripts(
    session: InterviewSession, stt: SpeechToText, storage: AudioStorage
) -> ScoringSession:
    turns = [ScoringTurn(t.speaker, _better_text(t, stt, storage)) for t in session.turns]
    return ScoringSession(turns, session.template)
