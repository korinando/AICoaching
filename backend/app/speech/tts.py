"""Text-to-speech with Piper, running locally on the CPU (Week 3 Step 6)."""

import io
import threading
import wave
from pathlib import Path
from typing import Protocol

from piper import PiperVoice
from piper.download_voices import download_voice


class TextToSpeechError(Exception):
    """The voice couldn't speak: its file is missing, or it crashed on this text."""


class TextToSpeech(Protocol):
    """Anything that turns text into WAV bytes. Tests use a fake."""

    def load(self) -> None:
        """Get ready ahead of the first request. Optional: synthesize does it if needed."""

    def synthesize(self, text: str) -> bytes:
        """The spoken text as a WAV file, or raises TextToSpeechError."""


class PiperTextToSpeech:
    """The voice is loaded once, at startup or on the first request (it takes a few seconds)."""

    def __init__(self, voice_path: Path, download_if_missing: bool = False) -> None:
        self.voice_path = voice_path
        # The server downloads a missing voice, like Whisper does for its models: in the cloud
        # the voice isn't in git or in the image (Week 7). Off by default, so a wrong path in
        # other code fails clearly instead of quietly downloading.
        self.download_if_missing = download_if_missing
        self._voice: PiperVoice | None = None
        # Sentences are spoken at the same time. Without this, each would load its own voice.
        self._load_lock = threading.Lock()

    def load(self) -> None:
        with self._load_lock:
            if self._voice is None:
                if not self.voice_path.exists() and self.download_if_missing:
                    self.voice_path.parent.mkdir(parents=True, exist_ok=True)
                    download_voice(self.voice_path.stem, self.voice_path.parent)
                if not self.voice_path.exists():
                    raise FileNotFoundError(
                        f"{self.voice_path} is missing. From backend/ run: uv run python -m "
                        f"piper.download_voices {self.voice_path.stem} --data-dir voices"
                    )
                self._voice = PiperVoice.load(self.voice_path)

    def synthesize(self, text: str) -> bytes:
        try:
            self.load()
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav_file:
                self._voice.synthesize_wav(text, wav_file)
            return buffer.getvalue()
        except Exception as e:
            raise TextToSpeechError(f"{type(e).__name__}: {e}") from e
