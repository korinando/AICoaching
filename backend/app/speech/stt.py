"""Speech-to-text: Whisper large-v3 on Groq's servers when GROQ_API_KEY is set, with the local
faster-whisper model as the backup; only the local model when it isn't. The local model runs on
the CPU, or on an NVIDIA GPU with WHISPER_DEVICE=cuda."""

import importlib.util
import io
import logging
import os
import sys
from pathlib import Path
from typing import Protocol

import httpx
import numpy as np
from faster_whisper import WhisperModel

from app.core.config import get_settings

# Nudges Whisper toward these spellings. Without it, technical words are easily misheard
# ("post grass Q L"). Words from the interview topics, not a sentence to transcribe.
VOCABULARY_HINT = (
    "REST API, HTTP, GET, POST, JSON, SQL, NoSQL, PostgreSQL, database index, Git, git fetch, "
    "git merge, git rebase, debugging, HTML, CSS, JavaScript, React, idempotent, "
    "machine learning, overfitting, LLM, prompt, RAG, embeddings, vector database, tokens."
)
# Limits the cost when Whisper gets stuck repeating a word on unclear audio. By default it
# fills the model's 448 tokens (prompt included) and retries 5 times. Real answers stayed
# under 60 tokens per segment, and most segments never retry, so their text doesn't change.
RETRY_TEMPERATURES = [0.0, 1.0]  # 1.0: the most random attempt, the one least likely to loop
MAX_TOKENS_PER_SEGMENT = 160


logger = logging.getLogger(__name__)

GROQ_TRANSCRIPTIONS_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


class SpeechToTextError(Exception):
    """The model couldn't run: it failed to load, or crashed on this audio."""


class SpeechToText(Protocol):
    """Anything that turns WAV bytes into text. Tests use a fake with scripted text."""

    def load(self) -> None:
        """Get ready ahead of the first request. Optional: transcribe does it if needed."""

    def transcribe(self, wav: bytes) -> str:
        """The spoken words, or "" if there's no speech. Raises SpeechToTextError on failure."""


def _use_pip_cuda_libraries() -> None:
    """On Windows, let faster-whisper find NVIDIA's cuBLAS and cuDNN.

    They come as pip packages (the "gpu" group in pyproject.toml), which put their DLLs in
    site-packages/nvidia/*/bin: a folder Windows doesn't search. Linux finds them by itself."""
    spec = importlib.util.find_spec("nvidia")
    if sys.platform != "win32" or spec is None or not spec.submodule_search_locations:
        return
    for root in spec.submodule_search_locations:
        for bin_dir in Path(root).glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"


class WhisperSpeechToText:
    """The model is loaded once, at startup or on the first request (the first run also
    downloads it). device="cuda" runs it on an NVIDIA GPU; if that fails, it falls back to the
    CPU, so a missing GPU or driver slows answers down but never stops them."""

    def __init__(self, model_name: str, device: str = "cpu", compute_type: str = "int8") -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model: WhisperModel | None = None

    def load(self) -> None:
        if self._model is not None:
            return
        if self.device != "cpu":
            try:
                _use_pip_cuda_libraries()
                self._model = self._create(self.device, self.compute_type)
                # Some missing GPU libraries only show up on the first transcription, so run one
                # now on a second of silence. It also sets up the GPU, so the first real answer
                # doesn't pay for that.
                # (segments is a generator: list() makes the transcription really run.)
                silence = np.zeros(16_000, dtype=np.float32)
                list(self._model.transcribe(silence, language="en", vad_filter=False)[0])
                logger.info("Whisper %s runs on the GPU (%s)", self.model_name, self.compute_type)
                return
            # CUDA errors are RuntimeError, a missing DLL OSError, a compute type the GPU lacks ValueError.
            except (RuntimeError, OSError, ValueError) as e:  # the CPU still works
                logger.warning(
                    "Whisper can't use the GPU (%s: %s); using the CPU", type(e).__name__, e
                )
                self._model = None
        # int8: smaller numbers inside the model, so faster on a CPU, for a very small loss of
        # accuracy.
        self._model = self._create("cpu", "int8")

    def _create(self, device: str, compute_type: str) -> WhisperModel:
        return WhisperModel(
            self.model_name,
            device=device,
            compute_type=compute_type,
            download_root=str(get_settings().whisper_models_dir),
        )

    def transcribe(self, wav: bytes) -> str:
        try:
            self.load()
            segments, _info = self._model.transcribe(
                io.BytesIO(wav),
                language="en",  # don't let an accent make it guess another language
                initial_prompt=VOCABULARY_HINT,
                temperature=RETRY_TEMPERATURES,
                max_new_tokens=MAX_TOKENS_PER_SEGMENT,
                # Voice activity detection: drop the silence first. On pure silence, Whisper
                # tends to invent text; with this it returns nothing.
                vad_filter=True,
            )
            # segments is a generator: the transcription really runs during this loop, so it
            # has to stay inside the try.
            return " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as e:
            raise SpeechToTextError(f"{type(e).__name__}: {e}") from e


class GroqSpeechToText:
    """Whisper on Groq's hardware: the large models, which take 7-10 s per 10 s of speech on a
    CPU, answer in well under a second there. The audio is sent to Groq."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_s: float = 10.0,
        transport: httpx.BaseTransport | None = None,  # tests pass a fake Groq here
    ) -> None:
        self.model = model
        # One client for the whole server: it keeps the connection open between answers.
        # 10 s: past that, the local backup is the quicker way to an answer.
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_s,
            transport=transport,
        )

    def load(self) -> None:
        """Nothing to load: the model lives on Groq's side."""

    def transcribe(self, wav: bytes) -> str:
        try:
            response = self._client.post(
                GROQ_TRANSCRIPTIONS_URL,
                files={"file": ("answer.wav", wav, "audio/wav")},
                data={
                    "model": self.model,
                    "language": "en",
                    "prompt": VOCABULARY_HINT,
                    "temperature": "0",
                    "response_format": "json",
                },
            )
            response.raise_for_status()
            return response.json()["text"].strip()
        except (httpx.HTTPError, KeyError, ValueError) as e:
            # Never the response body in the message: it could echo the request back.
            raise SpeechToTextError(f"Groq: {type(e).__name__}: {e}") from e


class FallbackSpeechToText:
    """Try the first model; if it fails (Groq down, rate limit, no network), the second. An
    answer is never lost because one service is having a bad minute."""

    def __init__(self, primary: SpeechToText, backup: SpeechToText) -> None:
        self.primary = primary
        self.backup = backup

    def load(self) -> None:
        self.primary.load()
        self.backup.load()  # loaded now, so a fallback doesn't also wait seconds for the model

    def transcribe(self, wav: bytes) -> str:
        try:
            return self.primary.transcribe(wav)
        except SpeechToTextError as e:
            logger.warning("Speech to text fell back to the local model: %s", e)
            return self.backup.transcribe(wav)
