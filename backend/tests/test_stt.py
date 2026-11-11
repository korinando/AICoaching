"""Word error rate, Groq, the local backup, and that failures become SpeechToTextError. No real
model and no real Groq here."""

from typing import ClassVar

import httpx
import pytest
from pydantic import SecretStr

from app.speech import stt as stt_module
from app.speech.stt import (
    GROQ_TRANSCRIPTIONS_URL,
    FallbackSpeechToText,
    GroqSpeechToText,
    SpeechToTextError,
    WhisperSpeechToText,
)
from scripts.check_stt import word_errors
from tests.fakes import FakeSpeechToText


@pytest.mark.parametrize(
    "reference, hypothesis, wrong, words",
    [
        ("add an index", "add an index", 0, 3),
        ("Add an index!", "add an INDEX", 0, 3),  # case and punctuation don't count
        ("add an index", "add a index", 1, 3),  # substituted
        ("add an index", "add index", 1, 3),  # deleted
        ("add an index", "add an extra index", 1, 3),  # inserted
        ("add an index", "", 3, 3),  # heard nothing
    ],
)
def test_word_errors(reference, hypothesis, wrong, words):
    assert word_errors(reference, hypothesis) == (wrong, words)


def test_model_failure_becomes_speech_to_text_error():
    """A model name that doesn't exist fails while loading, which stays inside our error."""
    stt = WhisperSpeechToText("no-such-model")

    with pytest.raises(SpeechToTextError):
        stt.transcribe(b"not used: the model fails to load first")


# --- Groq, and falling back to the local model ------------------------------------------------


def fake_groq(handler) -> GroqSpeechToText:
    """GroqSpeechToText talking to `handler` instead of the internet."""
    return GroqSpeechToText("test-key", "whisper-large-v3", transport=httpx.MockTransport(handler))


def test_groq_sends_the_audio_and_settings():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"text": "  I would add an index. "})

    assert fake_groq(handler).transcribe(b"RIFF-wav-bytes") == "I would add an index."
    request = seen[0]
    assert str(request.url) == GROQ_TRANSCRIPTIONS_URL
    assert request.headers["Authorization"] == "Bearer test-key"
    body = request.read()
    assert b"RIFF-wav-bytes" in body
    for field in (b"whisper-large-v3", b'name="language"', b"PostgreSQL"):  # model, en, the hint
        assert field in body


@pytest.mark.parametrize(
    "handler",
    [
        lambda _: httpx.Response(429, json={"error": "rate limit"}),
        lambda _: httpx.Response(500),
        lambda _: httpx.Response(200, json={"unexpected": "shape"}),
        lambda _: httpx.Response(200, text="not json"),
    ],
)
def test_groq_problems_become_speech_to_text_error(handler):
    with pytest.raises(SpeechToTextError):
        fake_groq(handler).transcribe(b"wav")


def test_groq_network_failure_becomes_speech_to_text_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("no network", request=request)

    with pytest.raises(SpeechToTextError):
        fake_groq(handler).transcribe(b"wav")


def test_fallback_uses_the_primary_when_it_works():
    primary, backup = FakeSpeechToText("from Groq"), FakeSpeechToText("from local")
    assert FallbackSpeechToText(primary, backup).transcribe(b"wav") == "from Groq"
    assert backup.calls == []  # the slow local model wasn't run for nothing


def test_fallback_uses_the_backup_when_the_primary_fails(caplog):
    primary, backup = FakeSpeechToText("from Groq"), FakeSpeechToText("from local")
    primary.error = SpeechToTextError("Groq: 429")
    assert FallbackSpeechToText(primary, backup).transcribe(b"wav") == "from local"
    assert "fell back" in caplog.text


def test_fallback_fails_only_when_both_fail():
    primary, backup = FakeSpeechToText(), FakeSpeechToText()
    primary.error = SpeechToTextError("Groq down")
    backup.error = SpeechToTextError("model broken")
    with pytest.raises(SpeechToTextError, match="model broken"):
        FallbackSpeechToText(primary, backup).transcribe(b"wav")


def test_settings_choose_the_speech_to_text(monkeypatch):
    from app.api import deps
    from app.core.config import get_settings

    for key, expected in (("", WhisperSpeechToText), ("gsk_test", FallbackSpeechToText)):
        settings = get_settings().model_copy(update={"groq_api_key": SecretStr(key)})
        monkeypatch.setattr(deps, "get_settings", lambda s=settings: s)
        deps.get_speech_to_text.cache_clear()
        assert isinstance(deps.get_speech_to_text(), expected)
    deps.get_speech_to_text.cache_clear()  # the next test gets the real settings again


# --- Running the local model on a GPU, or falling back to the CPU -----------------------------


class FakeWhisperModel:
    """Stands in for faster_whisper.WhisperModel: records how it was created, or fails like a
    machine without a usable GPU."""

    created: ClassVar[list[tuple[str, str]]] = []
    gpu_fails_at: ClassVar[str | None] = None  # "create" or "transcribe"

    def __init__(self, name, device, compute_type, download_root):
        if device == "cuda" and self.gpu_fails_at == "create":
            raise RuntimeError("CUDA driver version is insufficient")
        self.device = device
        FakeWhisperModel.created.append((device, compute_type))

    def transcribe(self, audio, **_options):
        if self.device == "cuda" and self.gpu_fails_at == "transcribe":
            raise RuntimeError("Library cublas64_12.dll is not found")
        return iter([]), None


@pytest.fixture
def fake_whisper(monkeypatch):
    monkeypatch.setattr(stt_module, "WhisperModel", FakeWhisperModel)
    FakeWhisperModel.created = []
    FakeWhisperModel.gpu_fails_at = None
    return FakeWhisperModel


def test_cpu_is_the_default(fake_whisper):
    WhisperSpeechToText("base.en").load()
    assert fake_whisper.created == [("cpu", "int8")]


def test_gpu_when_asked(fake_whisper):
    WhisperSpeechToText("turbo", "cuda", "int8_float16").load()
    assert fake_whisper.created == [("cuda", "int8_float16")]


@pytest.mark.parametrize("fails_at", ["create", "transcribe"])
def test_gpu_problems_fall_back_to_the_cpu(fake_whisper, caplog, fails_at):
    """A missing library can show up only on the first transcription: the warm-up catches it."""
    fake_whisper.gpu_fails_at = fails_at
    stt = WhisperSpeechToText("turbo", "cuda", "int8_float16")
    assert stt.transcribe(b"wav") == ""  # it still answers, on the CPU
    assert fake_whisper.created[-1] == ("cpu", "int8")
    assert "can't use the GPU" in caplog.text
