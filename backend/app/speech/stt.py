"""Speech-to-text with faster-whisper, running locally on the CPU (Week 3 Step 5)."""

import io
from typing import Protocol

from faster_whisper import WhisperModel

# Nudges Whisper toward these spellings. Without it, technical words are easily misheard
# ("post grass Q L"). Words from the interview topics, not a sentence to transcribe.
VOCABULARY_HINT = (
    "REST API, HTTP, GET, POST, JSON, SQL, NoSQL, PostgreSQL, database index, Git, git fetch, "
    "git merge, git rebase, debugging, HTML, CSS, JavaScript, React, idempotent."
)


class SpeechToTextError(Exception):
    """The model couldn't run: it failed to load, or crashed on this audio."""


class SpeechToText(Protocol):
    """Anything that turns WAV bytes into text. Tests use a fake with scripted text."""

    def transcribe(self, wav: bytes) -> str:
        """The spoken words, or "" if there's no speech. Raises SpeechToTextError on failure."""


class WhisperSpeechToText:
    """The model is loaded once, on the first request (the first run also downloads it)."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: WhisperModel | None = None

    def transcribe(self, wav: bytes) -> str:
        try:
            if self._model is None:
                # int8: smaller numbers inside the model, so faster on a CPU, for a very
                # small loss of accuracy.
                self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
            segments, _info = self._model.transcribe(
                io.BytesIO(wav),
                language="en",  # don't let an accent make it guess another language
                initial_prompt=VOCABULARY_HINT,
                # Voice activity detection: drop the silence first. On pure silence, Whisper
                # tends to invent text; with this it returns nothing.
                vad_filter=True,
            )
            # segments is a generator: the transcription really runs during this loop, so it
            # has to stay inside the try.
            return " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as e:
            raise SpeechToTextError(f"{type(e).__name__}: {e}") from e
