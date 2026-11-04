"""Text-to-speech with Piper, running locally on the CPU (Week 3 Step 6)."""

import io
import threading
import wave
from pathlib import Path
from typing import Protocol

from piper import PiperVoice


class TextToSpeechError(Exception):
    """The voice couldn't speak: its file is missing, or it crashed on this text."""


class TextToSpeech(Protocol):
    """Anything that turns text into WAV bytes. Tests use a fake."""

    def synthesize(self, text: str) -> bytes:
        """The spoken text as a WAV file, or raises TextToSpeechError."""


class PiperTextToSpeech:
    """The voice is loaded once, on the first request (it takes a few seconds)."""

    def __init__(self, voice_path: Path) -> None:
        self.voice_path = voice_path
        self._voice: PiperVoice | None = None
        self._load_lock = threading.Lock()

    def synthesize(self, text: str) -> bytes:
        try:
            with self._load_lock:
                if self._voice is None:
                    if not self.voice_path.exists():
                        raise FileNotFoundError(
                            f"{self.voice_path} is missing. From backend/ run: uv run python -m "
                            f"piper.download_voices {self.voice_path.stem} --data-dir voices"
                        )
                    self._voice = PiperVoice.load(self.voice_path)
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav_file:
                self._voice.synthesize_wav(text, wav_file)
            return buffer.getvalue()
        except Exception as e:
            raise TextToSpeechError(f"{type(e).__name__}: {e}") from e
